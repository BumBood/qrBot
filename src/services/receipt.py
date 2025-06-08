import re
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.receipt import Receipt
from models.user import User
from services.fnc_api import verify_receipt
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
    Обрабатывает фото чека, распознает QR-код и извлекает данные

    Args:
        user_id: ID пользователя
        photo_file_path: Путь к файлу с фото чека

    Returns:
        dict: Результат обработки с данными чека

    Raises:
        QRCodeError: Если не удалось распознать QR-код
    """
    try:
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
            raise QRCodeError("Формат QR-кода не соответствует ожидаемому")

        # Получаем данные из QR-кода
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

        return {"success": True, "receipt_id": new_receipt.id}

    except ReceiptValidationError as e:
        await session.rollback()
        logger.error(f"Ошибка валидации чека: {str(e)}")
        return {"success": False, "error": str(e)}

    except Exception as e:
        await session.rollback()
        logger.error(f"Непредвиденная ошибка при обработке чека: {str(e)}")
        return {"success": False, "error": "Произошла ошибка при обработке чека"}


async def verify_receipt_with_api(session: AsyncSession, receipt_id: int) -> dict:
    """
    Проверяет чек через API ФНС

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

        # Проверяем чек через API ФНС
        api_result = await verify_receipt(
            receipt.fn, receipt.fd, receipt.fpd, float(receipt.amount)
        )

        # Обновляем статус чека
        receipt.status = "verified"
        receipt.verification_date = datetime.now()

        # Если в ответе есть информация о товарах, анализируем ее
        if "items" in api_result:
            # Подсчитываем количество товаров "Айсида"
            aisida_count = 0
            for item in api_result.get("items", []):
                if "Айсида" in item.get("name", ""):
                    aisida_count += 1

            receipt.items_count = aisida_count

        # Если в ответе есть информация о магазине, сохраняем ее
        if "retailPlace" in api_result:
            receipt.pharmacy = api_result.get("retailPlace")

        await session.commit()

        return {
            "success": True,
            "status": "verified",
            "aisida_count": receipt.items_count,
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при проверке чека через API: {str(e)}")

        # Обновляем статус чека на "rejected" в случае ошибки
        if receipt:
            receipt.status = "rejected"
            receipt.verification_date = datetime.now()
            await session.commit()

        return {"success": False, "error": str(e)}
