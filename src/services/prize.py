import random
import string
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.prize import Prize
from models.receipt import Receipt
from logger import logger


def generate_coupon_code() -> str:
    """
    Генерирует уникальный промокод формата AISIDA-XXX-YYYY

    Returns:
        str: Сгенерированный промокод
    """
    # Генерируем случайные символы для кода
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=4))

    return f"AISIDA-{letters}-{numbers}"


async def issue_prize(
    session: AsyncSession, receipt_id: int, prize_type: str, phone_last4: str = None
) -> dict:
    """
    Выдает подарок за чек

    Args:
        session: Сессия базы данных
        receipt_id: ID чека
        prize_type: Тип подарка (coupon/phone)
        phone_last4: Последние 4 цифры телефона (для подарка типа phone)

    Returns:
        dict: Данные выданного подарка
    """
    try:
        # Проверяем существование чека
        receipt_query = await session.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        receipt = receipt_query.scalars().first()

        if not receipt:
            logger.error(f"Чек с ID {receipt_id} не найден")
            return {"success": False, "error": "Чек не найден"}

        # Проверяем, был ли уже выдан подарок за этот чек
        existing_prize = await session.execute(
            select(Prize).where(Prize.receipt_id == receipt_id)
        )

        if existing_prize.scalars().first():
            logger.error(f"Подарок за чек с ID {receipt_id} уже был выдан")
            return {"success": False, "error": "Подарок за этот чек уже был выдан"}

        # Создаем новый подарок
        new_prize = Prize(receipt_id=receipt_id, type=prize_type)

        # В зависимости от типа подарка
        if prize_type == "coupon":
            # Генерируем промокод
            code = generate_coupon_code()
            new_prize.code = code
        elif prize_type == "phone":
            # Проверяем наличие последних 4 цифр телефона
            if not phone_last4 or not phone_last4.isdigit() or len(phone_last4) != 4:
                logger.error(
                    f"Неверный формат последних 4 цифр телефона: {phone_last4}"
                )
                return {
                    "success": False,
                    "error": "Неверный формат последних 4 цифр телефона",
                }
            new_prize.phone_last4 = phone_last4
        else:
            logger.error(f"Неизвестный тип подарка: {prize_type}")
            return {"success": False, "error": "Неизвестный тип подарка"}

        # Сохраняем подарок в БД
        session.add(new_prize)
        await session.commit()

        logger.info(f"Выдан подарок типа {prize_type} за чек {receipt_id}")

        # Формируем ответ
        result = {"success": True, "prize_id": new_prize.id, "type": prize_type}

        if prize_type == "coupon":
            result["code"] = new_prize.code
        elif prize_type == "phone":
            result["phone_last4"] = new_prize.phone_last4

        return result

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при выдаче подарка: {str(e)}")
        return {
            "success": False,
            "error": f"Произошла ошибка при выдаче подарка: {str(e)}",
        }
