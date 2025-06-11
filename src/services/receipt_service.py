"""
Сервис для работы с чеками

УЛУЧШЕНИЯ СИСТЕМЫ РАСПОЗНАВАНИЯ ЧЕКОВ:

1. Гарантированное обновление статуса:
   - Статус чека ВСЕГДА изменяется после проверки
   - При успешной проверке: статус = "verified"
   - При ошибке API: статус = "rejected"
   - При исключении: статус = "rejected"

2. Улучшенная обработка ошибок:
   - Детальное логирование всех этапов проверки
   - Корректная обработка транзакций БД
   - Информативные сообщения об ошибках

3. Расширенная диагностика:
   - Функция check_pending_receipts() для массовой проверки
   - Функция get_receipt_statistics() для статистики
   - Административные команды /admin_stats и /admin_check_pending

4. Улучшенное распознавание товаров "Айсида":
   - Поиск как "Айсида", так и "айсида"
   - Подсчет всех вхождений в чеке
   - Детальное логирование найденных товаров

5. Улучшенный пользовательский интерфейс:
   - Информативные сообщения о статусе чека
   - Эмодзи для визуального различения статусов
   - Подробная информация в разделе "Мои чеки"
"""

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
FPD_PATTERN = r"^\d{1,15}$"  # от 1 до 15 цифр (расширил лимит)

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
            api_data = api_result["data"]
            check_data = api_data.get("json", {})

            logger.info(
                f"Извлекаю данные из API ответа: fiscalDriveNumber={check_data.get('fiscalDriveNumber')}, fiscalDocumentNumber={check_data.get('fiscalDocumentNumber')}, fiscalSign={check_data.get('fiscalSign')}, totalSum={check_data.get('totalSum')}"
            )

            # Получаем необходимые данные
            fn = str(check_data.get("fiscalDriveNumber", ""))
            fd = str(check_data.get("fiscalDocumentNumber", ""))
            fpd = str(check_data.get("fiscalSign", ""))
            amount = (
                float(check_data.get("totalSum", 0)) / 100
            )  # Сумма в копейках, переводим в рубли

            # Проверяем формат данных
            if not validate_receipt_data(fn, fd, fpd, amount):
                logger.error(
                    f"Ошибка валидации данных: fn={fn}, fd={fd}, fpd={fpd}, amount={amount}"
                )
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
                api_data = api_result["data"]
                check_data = api_data.get("json", {})

                logger.info(
                    f"Извлекаю данные из API ответа (второй вызов): fiscalDriveNumber={check_data.get('fiscalDriveNumber')}, fiscalDocumentNumber={check_data.get('fiscalDocumentNumber')}, fiscalSign={check_data.get('fiscalSign')}, totalSum={check_data.get('totalSum')}"
                )

                # Получаем необходимые данные
                fn = str(check_data.get("fiscalDriveNumber", ""))
                fd = str(check_data.get("fiscalDocumentNumber", ""))
                fpd = str(check_data.get("fiscalSign", ""))
                amount = (
                    float(check_data.get("totalSum", 0)) / 100
                )  # Сумма в копейках, переводим в рубли

                # Проверяем формат данных
                if not validate_receipt_data(fn, fd, fpd, amount):
                    logger.error(
                        f"Ошибка валидации данных (второй вызов): fn={fn}, fd={fd}, fpd={fpd}, amount={amount}"
                    )
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
    logger.info(
        f"Валидация данных чека: fn='{fn}' (len={len(fn)}), fd='{fd}' (len={len(fd)}), fpd='{fpd}' (len={len(fpd)}), amount={amount}"
    )

    if not re.match(FN_PATTERN, fn):
        logger.error(f"ФН не соответствует паттерну {FN_PATTERN}: '{fn}'")
        return False

    if not re.match(FD_PATTERN, fd):
        logger.error(f"ФД не соответствует паттерну {FD_PATTERN}: '{fd}'")
        return False

    if not re.match(FPD_PATTERN, fpd):
        logger.error(f"ФПД не соответствует паттерну {FPD_PATTERN}: '{fpd}'")
        return False

    if amount <= 0:
        logger.error(f"Сумма должна быть больше 0: {amount}")
        return False

    logger.info("Все поля прошли валидацию успешно")
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
    receipt = None
    try:
        # Получаем чек из БД
        receipt_query = await session.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        receipt = receipt_query.scalars().first()

        if not receipt:
            return {"success": False, "error": "Чек не найден"}

        # Логируем начало проверки
        logger.info(f"Начинаю проверку чека ID {receipt_id} через API")

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

        # Устанавливаем дату проверки в любом случае
        receipt.verification_date = datetime.now()

        logger.info(
            f"Чек {receipt_id} - текущий статус до обработки API: '{receipt.status}'"
        )

        # Обрабатываем результат API
        if not api_result["success"]:
            logger.error(
                f"API вернул ошибку для чека {receipt_id}: {api_result.get('error')}"
            )

            # Обновляем статус на "rejected" при неуспешном ответе API
            old_status = receipt.status
            receipt.status = "rejected"

            logger.info(
                f"Чек {receipt_id} - изменяю статус с '{old_status}' на 'rejected'"
            )

            await session.commit()

            # Проверяем что статус действительно изменился
            await session.refresh(receipt)
            logger.info(f"Чек {receipt_id} - статус после commit: '{receipt.status}'")

            return {
                "success": False,
                "error": api_result.get("error", "Ошибка при проверке чека"),
            }

            # API вернул успешный результат
        logger.info(f"API успешно проверил чек {receipt_id}")

        # Обновляем статус чека на "verified"
        old_status = receipt.status
        receipt.status = "verified"

        logger.info(f"Чек {receipt_id} - изменяю статус с '{old_status}' на 'verified'")

        # Обрабатываем данные из API ответа
        api_data = api_result.get("data", {})
        check_data = api_data.get("json", {})

        # Если в ответе есть информация о товарах, анализируем ее
        items_data = check_data.get("items", [])
        aisida_count = 0

        if items_data:
            # Подсчитываем количество товаров "Айсида"
            for item in items_data:
                item_name = item.get("name", "")
                if "Айсида" in item_name or "айсида" in item_name.lower():
                    aisida_count += 1
                    logger.info(f"Найден товар Айсида: {item_name}")

            receipt.items_count = aisida_count
            logger.info(
                f"Общее количество товаров Айсида в чеке {receipt_id}: {aisida_count}"
            )

        # Если в ответе есть информация о магазине, сохраняем ее
        retail_place = check_data.get("retailPlaceAddress")
        if retail_place:
            receipt.pharmacy = retail_place

        # Сохраняем изменения
        await session.commit()

        # Проверяем что статус действительно изменился
        await session.refresh(receipt)
        logger.info(
            f"Чек {receipt_id} - статус после commit: '{receipt.status}', данные сохранены"
        )

        return {
            "success": True,
            "status": "verified",
            "aisida_count": receipt.items_count,
            "pharmacy": receipt.pharmacy,
        }

    except Exception as e:
        # Логируем ошибку
        logger.error(f"Исключение при проверке чека {receipt_id} через API: {str(e)}")

        try:
            # Откатываем транзакцию
            await session.rollback()

            # Если receipt определен, обновляем его статус на "rejected"
            if receipt is not None:
                old_status = receipt.status
                logger.info(
                    f"Обновляю статус чека {receipt_id} с '{old_status}' на 'rejected' из-за исключения"
                )

                # Устанавливаем статус и дату проверки
                receipt.status = "rejected"
                receipt.verification_date = datetime.now()

                # Сохраняем изменения в новой транзакции
                await session.commit()

                # Проверяем что статус действительно изменился
                await session.refresh(receipt)
                logger.info(
                    f"Чек {receipt_id} - статус после commit: '{receipt.status}'"
                )
            else:
                logger.error(
                    f"Не удалось обновить статус чека {receipt_id} - объект чека не найден"
                )

        except Exception as inner_e:
            # Если произошла ошибка при обработке исключения, логируем её
            logger.error(
                f"Критическая ошибка при обработке исключения для чека {receipt_id}: {str(inner_e)}"
            )

            # Пытаемся сделать rollback еще раз
            try:
                await session.rollback()
            except:
                pass

        return {
            "success": False,
            "error": f"Произошла ошибка при проверке чека: {str(e)}",
        }


async def check_pending_receipts(session: AsyncSession) -> dict:
    """
    Проверяет все чеки со статусом 'pending' и обновляет их статус

    Args:
        session: Сессия базы данных

    Returns:
        dict: Результат проверки с количеством обработанных чеков
    """
    try:
        # Получаем все чеки со статусом 'pending'
        pending_receipts_query = await session.execute(
            select(Receipt).where(Receipt.status == "pending")
        )
        pending_receipts = pending_receipts_query.scalars().all()

        if not pending_receipts:
            logger.info("Нет чеков со статусом 'pending' для проверки")
            return {
                "success": True,
                "message": "Нет чеков для проверки",
                "processed": 0,
                "verified": 0,
                "rejected": 0,
            }

        logger.info(
            f"Найдено {len(pending_receipts)} чеков со статусом 'pending' для проверки"
        )

        verified_count = 0
        rejected_count = 0

        for receipt in pending_receipts:
            logger.info(f"Проверяю чек ID {receipt.id}")

            # Проверяем каждый чек
            result = await verify_receipt_with_api(session, receipt.id)

            if result["success"]:
                verified_count += 1
                logger.info(f"Чек ID {receipt.id} подтвержден")
            else:
                rejected_count += 1
                logger.info(f"Чек ID {receipt.id} отклонен: {result.get('error')}")

        total_processed = verified_count + rejected_count

        logger.info(
            f"Обработано чеков: {total_processed}, подтверждено: {verified_count}, отклонено: {rejected_count}"
        )

        return {
            "success": True,
            "message": f"Обработано {total_processed} чеков",
            "processed": total_processed,
            "verified": verified_count,
            "rejected": rejected_count,
        }

    except Exception as e:
        logger.error(f"Ошибка при проверке висящих чеков: {str(e)}")
        return {"success": False, "error": f"Ошибка при проверке: {str(e)}"}


async def get_receipt_statistics(session: AsyncSession, user_id: int = None) -> dict:
    """
    Получает статистику по чекам

    Args:
        session: Сессия базы данных
        user_id: ID пользователя (если нужна статистика по конкретному пользователю)

    Returns:
        dict: Статистика чеков
    """
    try:
        base_query = select(Receipt)
        if user_id:
            base_query = base_query.where(Receipt.user_id == user_id)

        # Получаем все чеки
        all_receipts_query = await session.execute(base_query)
        all_receipts = all_receipts_query.scalars().all()

        # Подсчитываем статистику
        total = len(all_receipts)
        pending = len([r for r in all_receipts if r.status == "pending"])
        verified = len([r for r in all_receipts if r.status == "verified"])
        rejected = len([r for r in all_receipts if r.status == "rejected"])

        return {
            "success": True,
            "total": total,
            "pending": pending,
            "verified": verified,
            "rejected": rejected,
            "user_id": user_id,
        }

    except Exception as e:
        logger.error(f"Ошибка при получении статистики чеков: {str(e)}")
        return {"success": False, "error": f"Ошибка при получении статистики: {str(e)}"}


async def test_receipt_status_update(
    session: AsyncSession, receipt_id: int, new_status: str
) -> dict:
    """
    Тестовая функция для проверки изменения статуса чека

    Args:
        session: Сессия базы данных
        receipt_id: ID чека
        new_status: Новый статус для установки

    Returns:
        dict: Результат операции
    """
    try:
        logger.info(f"ТЕСТ: Начинаю тестирование изменения статуса чека {receipt_id}")

        # Получаем чек из БД
        receipt_query = await session.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        receipt = receipt_query.scalars().first()

        if not receipt:
            return {"success": False, "error": "Чек не найден"}

        old_status = receipt.status
        logger.info(f"ТЕСТ: Чек {receipt_id} - текущий статус: '{old_status}'")

        # Изменяем статус
        receipt.status = new_status
        receipt.verification_date = datetime.now()

        logger.info(f"ТЕСТ: Чек {receipt_id} - устанавливаю статус: '{new_status}'")

        # Сохраняем изменения
        await session.commit()

        # Проверяем что статус изменился
        await session.refresh(receipt)
        final_status = receipt.status

        logger.info(
            f"ТЕСТ: Чек {receipt_id} - финальный статус после commit: '{final_status}'"
        )

        success = final_status == new_status

        return {
            "success": success,
            "old_status": old_status,
            "new_status": new_status,
            "final_status": final_status,
            "message": f"Статус {'изменен' if success else 'НЕ изменен'}",
        }

    except Exception as e:
        logger.error(
            f"ТЕСТ: Ошибка при тестировании статуса чека {receipt_id}: {str(e)}"
        )
        return {"success": False, "error": f"Ошибка при тестировании: {str(e)}"}
