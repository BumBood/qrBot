"""
Скрипт для миграции промокодов из файлов в базу данных

Запуск: python migrate_promocodes.py
"""

import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, Base

# Импортируем все модели, чтобы SQLAlchemy знал о таблицах
from models import User, Receipt, Prize, WeeklyLottery, Promocode
from services.promocode_service import promocode_service
from logger import logger


async def migrate_promocodes_from_files():
    """
    Мигрирует промокоды из файлов в базу данных
    """
    try:
        # Сначала создаем таблицы, если их нет
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Проверили создание таблиц в БД")

        async with AsyncSession(engine) as session:
            promocodes_200_file = "data/promocodes/promocodes_200.txt"
            promocodes_500_file = "data/promocodes/promocodes_500.txt"

            total_migrated = 0

            # Миграция промокодов на 200р
            if os.path.exists(promocodes_200_file):
                logger.info(f"Мигрируем промокоды из {promocodes_200_file}")

                with open(promocodes_200_file, "r", encoding="utf-8") as f:
                    codes_200 = [line.strip() for line in f.readlines() if line.strip()]

                if codes_200:
                    result = await promocode_service.add_promocodes(
                        session, codes_200, 200
                    )
                    if result["success"]:
                        logger.info(
                            f"Добавлено {result['added_count']} промокодов на 200р, пропущено {result['skipped_count']}"
                        )
                        total_migrated += result["added_count"]
                    else:
                        logger.error(
                            f"Ошибка при миграции промокодов 200р: {result['error']}"
                        )
                else:
                    logger.info("Файл промокодов 200р пустой")
            else:
                logger.warning(f"Файл {promocodes_200_file} не найден")

            # Миграция промокодов на 500р
            if os.path.exists(promocodes_500_file):
                logger.info(f"Мигрируем промокоды из {promocodes_500_file}")

                with open(promocodes_500_file, "r", encoding="utf-8") as f:
                    codes_500 = [line.strip() for line in f.readlines() if line.strip()]

                if codes_500:
                    result = await promocode_service.add_promocodes(
                        session, codes_500, 500
                    )
                    if result["success"]:
                        logger.info(
                            f"Добавлено {result['added_count']} промокодов на 500р, пропущено {result['skipped_count']}"
                        )
                        total_migrated += result["added_count"]
                    else:
                        logger.error(
                            f"Ошибка при миграции промокодов 500р: {result['error']}"
                        )
                else:
                    logger.info("Файл промокодов 500р пустой")
            else:
                logger.warning(f"Файл {promocodes_500_file} не найден")

            # Получаем итоговую статистику
            stats = await promocode_service.get_promocodes_stats(session)

            logger.info("=" * 50)
            logger.info("МИГРАЦИЯ ЗАВЕРШЕНА")
            logger.info(f"Всего мигрировано промокодов: {total_migrated}")
            logger.info(f"Итоговая статистика в БД:")
            logger.info(f"  - Всего промокодов: {stats['total_count']}")
            logger.info(
                f"  - Промокоды 200р: {stats['promo_200_total']} (доступно: {stats['available_200']})"
            )
            logger.info(
                f"  - Промокоды 500р: {stats['promo_500_total']} (доступно: {stats['available_500']})"
            )
            logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Ошибка при миграции промокодов: {str(e)}")


async def main():
    """
    Главная функция
    """
    logger.info("Начинаем миграцию промокодов из файлов в базу данных...")
    await migrate_promocodes_from_files()


if __name__ == "__main__":
    asyncio.run(main())
