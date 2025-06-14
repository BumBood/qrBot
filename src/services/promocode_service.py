from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from models.promocode_model import Promocode
from models.prize_model import Prize
from logger import logger


class PromoCodeService:
    """Сервис для работы с промокодами в базе данных"""

    @staticmethod
    async def add_promocodes(
        session: AsyncSession, codes: List[str], discount_amount: int
    ) -> dict:
        """
        Добавляет промокоды в базу данных

        Args:
            session: Сессия базы данных
            codes: Список промокодов для добавления
            discount_amount: Размер скидки (200 или 500)

        Returns:
            dict: Результат операции
        """
        try:
            if discount_amount not in [200, 500]:
                return {
                    "success": False,
                    "error": "Размер скидки должен быть 200 или 500",
                }

            added_count = 0
            skipped_count = 0
            errors = []

            for code in codes:
                code = code.strip()
                if not code:
                    continue

                # Проверяем, существует ли уже такой промокод
                existing = await session.execute(
                    select(Promocode).where(Promocode.code == code)
                )

                if existing.scalars().first():
                    skipped_count += 1
                    errors.append(f"Промокод {code} уже существует")
                    continue

                # Добавляем промокод
                promocode = Promocode(
                    code=code,
                    discount_amount=discount_amount,
                    is_used=False,
                    is_active=True,
                )
                session.add(promocode)
                added_count += 1

            await session.commit()

            logger.info(
                f"Добавлено {added_count} промокодов на {discount_amount} руб., пропущено {skipped_count}"
            )

            return {
                "success": True,
                "added_count": added_count,
                "skipped_count": skipped_count,
                "errors": errors,
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении промокодов: {str(e)}")
            return {
                "success": False,
                "error": f"Ошибка при добавлении промокодов: {str(e)}",
            }

    @staticmethod
    async def get_available_promocode(
        session: AsyncSession, discount_amount: int
    ) -> Optional[Promocode]:
        """
        Получает доступный промокод для указанной скидки

        Args:
            session: Сессия базы данных
            discount_amount: Размер скидки (200 или 500)

        Returns:
            Optional[Promocode]: Промокод или None если промокоды закончились
        """
        try:
            # Ищем доступный промокод
            query = await session.execute(
                select(Promocode)
                .where(
                    and_(
                        Promocode.discount_amount == discount_amount,
                        Promocode.is_used == False,
                        Promocode.is_active == True,
                    )
                )
                .limit(1)
            )

            promocode = query.scalars().first()

            if not promocode:
                logger.warning(
                    f"Все промокоды на {discount_amount} руб. закончились или отключены"
                )
                return None

            # Помечаем промокод как использованный
            promocode.is_used = True
            promocode.used_at = datetime.now()
            await session.commit()

            logger.info(f"Выдан промокод {promocode.code} на {discount_amount} руб.")
            return promocode

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при получении промокода: {str(e)}")
            return None

    @staticmethod
    async def get_promocodes_stats(session: AsyncSession) -> dict:
        """
        Получает статистику по промокодам

        Args:
            session: Сессия базы данных

        Returns:
            dict: Статистика промокодов
        """
        try:
            from sqlalchemy import func

            # Общее количество промокодов
            total_query = await session.execute(select(func.count(Promocode.id)))
            total_count = total_query.scalar() or 0

            # Количество по типам скидок
            promo_200_total = await session.execute(
                select(func.count(Promocode.id)).where(Promocode.discount_amount == 200)
            )
            promo_200_total = promo_200_total.scalar() or 0

            promo_500_total = await session.execute(
                select(func.count(Promocode.id)).where(Promocode.discount_amount == 500)
            )
            promo_500_total = promo_500_total.scalar() or 0

            # Использованные промокоды
            used_200 = await session.execute(
                select(func.count(Promocode.id)).where(
                    and_(Promocode.discount_amount == 200, Promocode.is_used == True)
                )
            )
            used_200 = used_200.scalar() or 0

            used_500 = await session.execute(
                select(func.count(Promocode.id)).where(
                    and_(Promocode.discount_amount == 500, Promocode.is_used == True)
                )
            )
            used_500 = used_500.scalar() or 0

            # Доступные промокоды
            available_200 = await session.execute(
                select(func.count(Promocode.id)).where(
                    and_(
                        Promocode.discount_amount == 200,
                        Promocode.is_used == False,
                        Promocode.is_active == True,
                    )
                )
            )
            available_200 = available_200.scalar() or 0

            available_500 = await session.execute(
                select(func.count(Promocode.id)).where(
                    and_(
                        Promocode.discount_amount == 500,
                        Promocode.is_used == False,
                        Promocode.is_active == True,
                    )
                )
            )
            available_500 = available_500.scalar() or 0

            return {
                "total_count": total_count,
                "promo_200_total": promo_200_total,
                "promo_500_total": promo_500_total,
                "used_200": used_200,
                "used_500": used_500,
                "available_200": available_200,
                "available_500": available_500,
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики промокодов: {str(e)}")
            return {
                "total_count": 0,
                "promo_200_total": 0,
                "promo_500_total": 0,
                "used_200": 0,
                "used_500": 0,
                "available_200": 0,
                "available_500": 0,
            }

    @staticmethod
    async def deactivate_promocode(session: AsyncSession, promocode_id: int) -> dict:
        """
        Деактивирует промокод

        Args:
            session: Сессия базы данных
            promocode_id: ID промокода

        Returns:
            dict: Результат операции
        """
        try:
            query = await session.execute(
                select(Promocode).where(Promocode.id == promocode_id)
            )
            promocode = query.scalars().first()

            if not promocode:
                return {"success": False, "error": "Промокод не найден"}

            promocode.is_active = False
            await session.commit()

            logger.info(f"Промокод {promocode.code} деактивирован")
            return {
                "success": True,
                "message": f"Промокод {promocode.code} деактивирован",
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при деактивации промокода: {str(e)}")
            return {
                "success": False,
                "error": f"Ошибка при деактивации промокода: {str(e)}",
            }

    @staticmethod
    async def activate_promocode(session: AsyncSession, promocode_id: int) -> dict:
        """
        Активирует промокод

        Args:
            session: Сессия базы данных
            promocode_id: ID промокода

        Returns:
            dict: Результат операции
        """
        try:
            query = await session.execute(
                select(Promocode).where(Promocode.id == promocode_id)
            )
            promocode = query.scalars().first()

            if not promocode:
                return {"success": False, "error": "Промокод не найден"}

            promocode.is_active = True
            await session.commit()

            logger.info(f"Промокод {promocode.code} активирован")
            return {
                "success": True,
                "message": f"Промокод {promocode.code} активирован",
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при активации промокода: {str(e)}")
            return {
                "success": False,
                "error": f"Ошибка при активации промокода: {str(e)}",
            }

    @staticmethod
    async def get_promocodes_list(
        session: AsyncSession,
        discount_amount: Optional[int] = None,
        is_used: Optional[bool] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Promocode]:
        """
        Получает список промокодов с фильтрацией

        Args:
            session: Сессия базы данных
            discount_amount: Размер скидки для фильтрации (опционально)
            is_used: Статус использования для фильтрации (опционально)
            is_active: Статус активности для фильтрации (опционально)
            limit: Максимальное количество промокодов

        Returns:
            List[Promocode]: Список промокодов
        """
        try:
            query = select(Promocode)

            conditions = []
            if discount_amount is not None:
                conditions.append(Promocode.discount_amount == discount_amount)
            if is_used is not None:
                conditions.append(Promocode.is_used == is_used)
            if is_active is not None:
                conditions.append(Promocode.is_active == is_active)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(Promocode.created_at.desc()).limit(limit)

            result = await session.execute(query)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Ошибка при получении списка промокодов: {str(e)}")
            return []


# Создаем экземпляр сервиса
promocode_service = PromoCodeService()
