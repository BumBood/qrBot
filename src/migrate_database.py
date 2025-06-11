"""
Миграция базы данных для добавления системы промокодов

Запуск: python migrate_database.py
"""

import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import engine, Base

# Импортируем все модели, чтобы SQLAlchemy знал о таблицах
from models import User, Receipt, Prize, WeeklyLottery, Promocode
from services.promocode_service import promocode_service
from logger import logger


async def check_table_exists(session: AsyncSession, table_name: str) -> bool:
    """Проверяет, существует ли таблица в БД"""
    try:
        result = await session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
            ),
            {"table_name": table_name},
        )
        return result.scalar()
    except Exception as e:
        logger.error(f"Ошибка при проверке таблицы {table_name}: {str(e)}")
        return False


async def check_column_exists(
    session: AsyncSession, table_name: str, column_name: str
) -> bool:
    """Проверяет, существует ли колонка в таблице"""
    try:
        result = await session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = :table_name AND column_name = :column_name
                )
            """
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        return result.scalar()
    except Exception as e:
        logger.error(
            f"Ошибка при проверке колонки {column_name} в таблице {table_name}: {str(e)}"
        )
        return False


async def migrate_database():
    """
    Выполняет миграцию базы данных
    """
    try:
        logger.info("Начинаем миграцию базы данных...")

        async with AsyncSession(engine) as session:
            # 1. Создаем все стандартные таблицы
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("✅ Проверили создание всех таблиц")

            # 2. Проверяем, существует ли таблица promocodes
            promocodes_exists = await check_table_exists(session, "promocodes")
            if promocodes_exists:
                logger.info("✅ Таблица promocodes уже существует")
            else:
                logger.info("📝 Создаем таблицу promocodes...")
                # Таблица должна была создаться через Base.metadata.create_all()
                promocodes_exists = await check_table_exists(session, "promocodes")
                if promocodes_exists:
                    logger.info("✅ Таблица promocodes создана")
                else:
                    logger.error("❌ Не удалось создать таблицу promocodes")

            # 3. Проверяем, существует ли поле promocode_id в таблице prizes
            promocode_id_exists = await check_column_exists(
                session, "prizes", "promocode_id"
            )
            if promocode_id_exists:
                logger.info("✅ Поле promocode_id в таблице prizes уже существует")
            else:
                logger.info("📝 Добавляем поле promocode_id в таблицу prizes...")
                try:
                    await session.execute(
                        text(
                            "ALTER TABLE prizes ADD COLUMN promocode_id INTEGER REFERENCES promocodes(id)"
                        )
                    )
                    await session.commit()
                    logger.info("✅ Поле promocode_id добавлено в таблицу prizes")
                except Exception as e:
                    logger.error(
                        f"❌ Ошибка при добавлении поля promocode_id: {str(e)}"
                    )
                    await session.rollback()

            # 4. Мигрируем промокоды из файлов, если они есть
            await migrate_promocodes_from_files(session)

            # 5. Получаем финальную статистику
            stats = await promocode_service.get_promocodes_stats(session)

            logger.info("=" * 60)
            logger.info("🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО")
            logger.info("=" * 60)
            logger.info("📊 Итоговая статистика:")
            logger.info(f"  📦 Всего промокодов в БД: {stats['total_count']}")
            logger.info(
                f"  💰 Промокоды 200р: {stats['promo_200_total']} (доступно: {stats['available_200']})"
            )
            logger.info(
                f"  💎 Промокоды 500р: {stats['promo_500_total']} (доступно: {stats['available_500']})"
            )
            logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при миграции: {str(e)}")
        raise


async def migrate_promocodes_from_files(session: AsyncSession):
    """
    Мигрирует промокоды из файлов в базу данных (если файлы существуют)
    """
    try:
        promocodes_200_file = "data/promocodes/promocodes_200.txt"
        promocodes_500_file = "data/promocodes/promocodes_500.txt"

        total_migrated = 0

        # Миграция промокодов на 200р
        if os.path.exists(promocodes_200_file):
            logger.info(f"📁 Найден файл {promocodes_200_file}, мигрируем...")

            with open(promocodes_200_file, "r", encoding="utf-8") as f:
                codes_200 = [line.strip() for line in f.readlines() if line.strip()]

            if codes_200:
                result = await promocode_service.add_promocodes(session, codes_200, 200)
                if result["success"]:
                    logger.info(
                        f"✅ Добавлено {result['added_count']} промокодов на 200р, пропущено {result['skipped_count']}"
                    )
                    total_migrated += result["added_count"]
                else:
                    logger.error(
                        f"❌ Ошибка при миграции промокодов 200р: {result['error']}"
                    )
            else:
                logger.info("⚠️ Файл промокодов 200р пустой")
        else:
            logger.info(f"ℹ️ Файл {promocodes_200_file} не найден, пропускаем")

        # Миграция промокодов на 500р
        if os.path.exists(promocodes_500_file):
            logger.info(f"📁 Найден файл {promocodes_500_file}, мигрируем...")

            with open(promocodes_500_file, "r", encoding="utf-8") as f:
                codes_500 = [line.strip() for line in f.readlines() if line.strip()]

            if codes_500:
                result = await promocode_service.add_promocodes(session, codes_500, 500)
                if result["success"]:
                    logger.info(
                        f"✅ Добавлено {result['added_count']} промокодов на 500р, пропущено {result['skipped_count']}"
                    )
                    total_migrated += result["added_count"]
                else:
                    logger.error(
                        f"❌ Ошибка при миграции промокодов 500р: {result['error']}"
                    )
            else:
                logger.info("⚠️ Файл промокодов 500р пустой")
        else:
            logger.info(f"ℹ️ Файл {promocodes_500_file} не найден, пропускаем")

        if total_migrated > 0:
            logger.info(f"✅ Всего мигрировано промокодов из файлов: {total_migrated}")
        else:
            logger.info(
                "ℹ️ Промокоды из файлов не мигрировались (файлы отсутствуют или пустые)"
            )

    except Exception as e:
        logger.error(f"❌ Ошибка при миграции промокодов из файлов: {str(e)}")


async def create_sample_promocodes(session: AsyncSession):
    """
    Создает тестовые промокоды, если в БД их нет
    """
    try:
        stats = await promocode_service.get_promocodes_stats(session)

        if stats["total_count"] == 0:
            logger.info("📝 В БД нет промокодов, создаем тестовые...")

            # Создаем тестовые промокоды 200р
            test_codes_200 = [f"TEST200-{i:03d}" for i in range(1, 11)]  # 10 промокодов
            result_200 = await promocode_service.add_promocodes(
                session, test_codes_200, 200
            )

            # Создаем тестовые промокоды 500р
            test_codes_500 = [f"TEST500-{i:03d}" for i in range(1, 6)]  # 5 промокодов
            result_500 = await promocode_service.add_promocodes(
                session, test_codes_500, 500
            )

            if result_200["success"] and result_500["success"]:
                total_created = result_200["added_count"] + result_500["added_count"]
                logger.info(f"✅ Создано {total_created} тестовых промокодов")
                logger.info(f"  💰 Промокоды 200р: {result_200['added_count']}")
                logger.info(f"  💎 Промокоды 500р: {result_500['added_count']}")
            else:
                logger.error("❌ Ошибка при создании тестовых промокодов")
        else:
            logger.info(
                f"ℹ️ В БД уже есть {stats['total_count']} промокодов, тестовые не создаем"
            )

    except Exception as e:
        logger.error(f"❌ Ошибка при создании тестовых промокодов: {str(e)}")


async def main():
    """
    Главная функция
    """
    logger.info("🚀 Запуск миграции базы данных для системы промокодов")

    try:
        await migrate_database()

        # Спрашиваем, создать ли тестовые промокоды
        async with AsyncSession(engine) as session:
            await create_sample_promocodes(session)

        logger.info("🎉 Миграция завершена успешно!")
        logger.info(
            "💡 Теперь можно запускать бота и использовать админку для управления промокодами"
        )

    except Exception as e:
        logger.error(f"💥 Миграция завершилась с ошибкой: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
