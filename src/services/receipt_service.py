import re
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.receipt_model import Receipt
from models.user_model import User
from services.check_api_service import verify_check
from config import PROVERKACHEKA_API_TOKEN
from errors import ReceiptValidationError, QRCodeError
from logger import logger

# Регулярное выражение для проверки формата данных чека
FN_PATTERN = r"^\d{16}$|^\d{17}$"  # 16 или 17 цифр
FD_PATTERN = r"^\d{1,6}$"  # от 1 до 6 цифр
FPD_PATTERN = r"^\d{1,10}$"  # от 1 до 10 цифр

# Регулярное выражение для извлечения данных из QR-кода
QR_PATTERN = r"t=(?P<date>\d{8}T\d{6})&s=(?P<amount>[\d.]+)&fn=(?P<fn>\d+)&i=(?P<fd>\d+)&fp=(?P<fpd>\d+)"


async def process_receipt_photo(user_id: int, photo_file_path: str) -> dict:
    """
    Обрабатывает фото чека, распознает QR-код и извлекает данные или использует API для распознавания

    Args:
        user_id: ID пользователя
        photo_file_path: Путь к файлу с фото чека

    Returns:
        dict: Результат обработки с данными чека

    Raises:
        QRCodeError: Если не удалось распознать QR-код
    """
    try:
        # Сначала пробуем использовать API proverkacheka.com для распознавания QR-кода
        api_result = await verify_check(
            token=PROVERKACHEKA_API_TOKEN, qr_file_path=photo_file_path
        )

        if api_result["success"] and api_result.get("data"):
            # Извлекаем данные из ответа API
            check_data = api_result["data"]

            # Получаем необходимые данные
            fn = check_data.get("fn", "")
            fd = check_data.get("fiscalDocumentNumber", "")
            fpd = check_data.get("fiscalSign", "")
            amount = (
                float(check_data.get("totalSum", 0)) / 100
            )  # Сумма в копейках, переводим в рубли

            # Проверяем формат данных
            if not validate_receipt_data(fn, fd, fpd, amount):
                raise ReceiptValidationError("Неверный формат данных чека")

            return {"success": True, "fn": fn, "fd": fd, "fpd": fpd, "amount": amount}

        # Если API не смог распознать, пробуем локальное распознавание
        logger.info("API не смог распознать QR-код, пробуем локальное распознавание")

        # Загружаем изображение
        image = cv2.imread(photo_file_path)
        if image is None:
            raise QRCodeError("Не удалось загрузить изображение")

        # Распознаем QR-код
        decoded_objects = decode(image)
        if not decoded_objects:
            raise QRCodeError("QR-код не найден на изображении")

        # Получаем данные из QR-кода
        qr_data = decoded_objects[0].data.decode("utf-8")
        logger.info(f"Распознан QR-код: {qr_data}")

        # Извлекаем данные с помощью регулярного выражения
        match = re.search(QR_PATTERN, qr_data)
        if not match:
            # Если не удалось извлечь данные по шаблону, пробуем использовать API с сырыми данными QR-кода
            api_result = await verify_check(
                token=PROVERKACHEKA_API_TOKEN, qr_raw=qr_data
            )

            if api_result["success"] and api_result.get("data"):
                # Извлекаем данные из ответа API
                check_data = api_result["data"]

                # Получаем необходимые данные
                fn = check_data.get("fn", "")
                fd = check_data.get("fiscalDocumentNumber", "")
                fpd = check_data.get("fiscalSign", "")
                amount = (
                    float(check_data.get("totalSum", 0)) / 100
                )  # Сумма в копейках, переводим в рубли

                # Проверяем формат данных
                if not validate_receipt_data(fn, fd, fpd, amount):
                    raise ReceiptValidationError("Неверный формат данных чека")

                return {
                    "success": True,
                    "fn": fn,
                    "fd": fd,
                    "fpd": fpd,
                    "amount": amount,
                }
            else:
                raise QRCodeError(
                    "Формат QR-кода не соответствует ожидаемому и не распознан API"
                )

        # Получаем данные из QR-кода (если распознали локально)
        fn = match.group("fn")
        fd = match.group("fd")
        fpd = match.group("fpd")
        amount = float(match.group("amount"))

        # Проверяем формат данных
        if not validate_receipt_data(fn, fd, fpd, amount):
            raise ReceiptValidationError("Неверный формат данных чека")

        return {"success": True, "fn": fn, "fd": fd, "fpd": fpd, "amount": amount}

    except QRCodeError as e:
        logger.error(f"Ошибка при распознавании QR-кода: {str(e)}")
        return {"success": False, "error": str(e)}

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при обработке фото чека: {str(e)}")
        return {"success": False, "error": "Произошла ошибка при обработке фото"}


def validate_receipt_data(fn: str, fd: str, fpd: str, amount: float) -> bool:
    """
    Проверяет формат данных чека

    Args:
        fn: Номер ФН
        fd: Номер ФД
        fpd: Номер ФПД
        amount: Сумма чека

    Returns:
        bool: True, если формат данных корректный, иначе False
    """
    if not re.match(FN_PATTERN, fn):
        return False

    if not re.match(FD_PATTERN, fd):
        return False

    if not re.match(FPD_PATTERN, fpd):
        return False

    if amount <= 0:
        return False

    return True


async def process_manual_receipt(
    session: AsyncSession, user_id: int, fn: str, fd: str, fpd: str, amount: float
) -> dict:
    """
    Обрабатывает вручную введенные данные чека

    Args:
        session: Сессия базы данных
        user_id: ID пользователя
        fn: Номер ФН
        fd: Номер ФД
        fpd: Номер ФПД
        amount: Сумма чека

    Returns:
        dict: Результат обработки

    Raises:
        ReceiptValidationError: Если формат данных некорректный
    """
    try:
        # Проверяем формат данных
        if not validate_receipt_data(fn, fd, fpd, amount):
            raise ReceiptValidationError("Неверный формат данных чека")

        # Проверяем существование пользователя
        user_exists = await session.execute(select(User).where(User.id == user_id))
        user = user_exists.scalars().first()

        if not user:
            raise ReceiptValidationError("Пользователь не найден")

        # Проверяем, не был ли уже добавлен такой чек
        existing_receipt = await session.execute(
            select(Receipt).where(
                Receipt.user_id == user_id,
                Receipt.fn == fn,
                Receipt.fd == fd,
                Receipt.fpd == fpd,
            )
        )

        if existing_receipt.scalars().first():
            raise ReceiptValidationError("Этот чек уже был зарегистрирован")

        # Создаем новую запись в БД
        new_receipt = Receipt(
            user_id=user_id, fn=fn, fd=fd, fpd=fpd, amount=amount, status="pending"
        )

        session.add(new_receipt)
        await session.commit()

        # Обновляем объект, чтобы получить ID
        await session.refresh(new_receipt)

        return {"success": True, "receipt_id": new_receipt.id}

    except ReceiptValidationError as e:
        try:
            await session.rollback()
        except Exception:
            # Игнорируем ошибки при rollback
            pass

        logger.error(f"Ошибка валидации чека: {str(e)}")
        return {"success": False, "error": str(e)}

    except Exception as e:
        try:
            await session.rollback()
        except Exception:
            # Игнорируем ошибки при rollback
            pass

        logger.error(f"Непредвиденная ошибка при обработке чека: {str(e)}")
        return {"success": False, "error": "Произошла ошибка при обработке чека"}


async def verify_receipt_with_api(session: AsyncSession, receipt_id: int) -> dict:
    """
    Проверяет чек через API proverkacheka.com

    Args:
        session: Сессия базы данных
        receipt_id: ID чека

    Returns:
        dict: Результат проверки
    """
    try:
        # Получаем чек из БД
        receipt_query = await session.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        receipt = receipt_query.scalars().first()

        if not receipt:
            return {"success": False, "error": "Чек не найден"}

        # Проверяем чек через API proverkacheka.com
        # Форматируем время в формат YYYYMMDDTHHMM
        receipt_date = receipt.created_at.strftime("%Y%m%dT%H%M")

        api_result = await verify_check(
            token=PROVERKACHEKA_API_TOKEN,
            fn=receipt.fn,
            fd=receipt.fd,
            fp=receipt.fpd,
            time=receipt_date,
            n="1",  # Предполагаем, что это приход
            s=str(receipt.amount),
        )

        if not api_result["success"]:
            logger.error(
                f"Ошибка при проверке чека через API: {api_result.get('error')}"
            )

            # Обновляем статус чека на "rejected" в случае ошибки
            receipt.status = "rejected"
            receipt.verification_date = datetime.now()
            await session.commit()

            return {
                "success": False,
                "error": api_result.get("error", "Ошибка при проверке чека"),
            }

        # Обновляем статус чека
        receipt.status = "verified"
        receipt.verification_date = datetime.now()

        # Если в ответе есть информация о товарах, анализируем ее
        items_data = api_result.get("data", {}).get("items", [])
        aisida_count = 0

        if items_data:
            # Подсчитываем количество товаров "Айсида"
            for item in items_data:
                if "Айсида" in item.get("name", ""):
                    aisida_count += 1

            receipt.items_count = aisida_count

        # Если в ответе есть информация о магазине, сохраняем ее
        retail_place = api_result.get("data", {}).get("retailPlace")
        if retail_place:
            receipt.pharmacy = retail_place

        # Сохраняем изменения
        session.commit()

        return {
            "success": True,
            "status": "verified",
            "aisida_count": receipt.items_count,
        }

    except Exception as e:
        # Логируем ошибку
        logger.error(f"Ошибка при проверке чека через API: {str(e)}")

        try:
            # Пытаемся сделать rollback в безопасном режиме
            await session.rollback()

            # Если receipt определен, обновляем его статус
            if "receipt" in locals() and receipt:
                # Обновляем статус без использования вложенной транзакции
                receipt.status = "rejected"
                receipt.verification_date = datetime.now()

                # Коммитим изменения
                await session.commit()
        except Exception as inner_e:
            # Если произошла ошибка при обработке исключения, логируем её
            logger.error(f"Ошибка при обработке исключения: {str(inner_e)}")

        return {"success": False, "error": str(e)}
