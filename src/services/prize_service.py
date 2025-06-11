import os
import random
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.prize_model import Prize
from models.receipt_model import Receipt
from services.promocode_service import promocode_service
from logger import logger


class PromoCodeManager:
    """Менеджер для работы с промокодами (LEGACY - для обратной совместимости)"""

    def __init__(self):
        # Оставляем пути к файлам для возможной миграции данных
        self.promocodes_200_file = "data/promocodes/promocodes_200.txt"
        self.promocodes_500_file = "data/promocodes/promocodes_500.txt"

    def _load_promocodes(self, file_path: str) -> List[str]:
        """
        Загружает промокоды из файла (LEGACY)

        Args:
            file_path: Путь к файлу с промокодами

        Returns:
            List[str]: Список промокодов
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(
                    f"Файл с промокодами не найден: {file_path}. Используется база данных."
                )
                return []

            with open(file_path, "r", encoding="utf-8") as f:
                codes = [line.strip() for line in f.readlines() if line.strip()]

            logger.info(f"Загружено {len(codes)} промокодов из {file_path} (LEGACY)")
            return codes

        except Exception as e:
            logger.error(f"Ошибка при загрузке промокодов из {file_path}: {str(e)}")
            return []

    async def get_available_promocode(
        self, session: AsyncSession, discount_amount: int
    ) -> Optional[str]:
        """
        Получает доступный промокод для указанной скидки (LEGACY - переадресация на новый сервис)

        Args:
            session: Сессия базы данных
            discount_amount: Размер скидки (200 или 500)

        Returns:
            Optional[str]: Промокод или None если промокоды закончились
        """
        logger.warning(
            "Используется устаревший метод get_available_promocode. Переходим на новый сервис."
        )

        promocode = await promocode_service.get_available_promocode(
            session, discount_amount
        )
        return promocode.code if promocode else None


# Создаем экземпляр для обратной совместимости
promo_manager = PromoCodeManager()


async def issue_prize(session: AsyncSession, receipt_id: int, items_count: int) -> dict:
    """
    Выдает подарок за чек в зависимости от количества товаров Айсида

    Args:
        session: Сессия базы данных
        receipt_id: ID чека
        items_count: Количество товаров Айсида в чеке

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

        # Определяем размер скидки в зависимости от количества товаров
        if items_count == 1:
            discount_amount = 200
            prize_type = "promocode_200"
        elif items_count >= 2:
            discount_amount = 500
            prize_type = "promocode_500"
        else:
            logger.error(f"Некорректное количество товаров Айсида: {items_count}")
            return {"success": False, "error": "В чеке не найдены товары Айсида"}

        # Получаем доступный промокод из базы данных
        promocode = await promocode_service.get_available_promocode(
            session, discount_amount
        )

        if not promocode:
            logger.error(f"Промокоды на {discount_amount} руб. закончились")
            return {
                "success": False,
                "error": f"К сожалению, промокоды на скидку {discount_amount} руб. временно закончились",
            }

        # Создаем новый подарок с привязкой к промокоду в БД
        new_prize = Prize(
            receipt_id=receipt_id,
            type=prize_type,
            code=promocode.code,  # Дублируем код для обратной совместимости
            promocode_id=promocode.id,  # Новая связь с таблицей промокодов
            discount_amount=discount_amount,
            used=False,
        )

        # Сохраняем подарок в БД
        session.add(new_prize)
        await session.commit()

        # Обновляем объект, чтобы получить ID
        await session.refresh(new_prize)

        logger.info(
            f"Выдан промокод {promocode.code} на {discount_amount} руб. за чек {receipt_id} (ID промокода в БД: {promocode.id})"
        )

        return {
            "success": True,
            "prize_id": new_prize.id,
            "type": prize_type,
            "code": promocode.code,
            "discount_amount": discount_amount,
            "items_count": items_count,
            "promocode_id": promocode.id,
        }

    except Exception as e:
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(f"Ошибка при откате транзакции: {str(rollback_error)}")

        logger.error(f"Ошибка при выдаче подарка: {str(e)}")
        return {
            "success": False,
            "error": f"Произошла ошибка при выдаче подарка: {str(e)}",
        }
