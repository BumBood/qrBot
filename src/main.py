import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from sqlalchemy.ext.asyncio import AsyncSession

from config import BOT_TOKEN
from database import engine, Base, get_session
from handlers import (
    register_base_handlers,
    register_registration_handlers,
    register_receipt_handlers,
)
from logger import logger
from handlers.registration import register_user


async def on_startup(bot: Bot) -> None:
    """
    Выполняется при запуске бота
    """
    logger.info("Бот запущен")

    # Создаем таблицы в базе данных
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)  # Раскомментировать для сброса БД
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Таблицы в базе данных созданы")


async def on_shutdown(bot: Bot) -> None:
    """
    Выполняется при остановке бота
    """
    logger.info("Бот остановлен")


async def main() -> None:
    """
    Точка входа в приложение
    """
    # Проверяем наличие токена
    if not BOT_TOKEN:
        logger.error(
            "Токен бота не найден. Убедитесь, что переменная окружения BOT_TOKEN установлена."
        )
        return

    # Создаем экземпляр бота и диспетчера
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.CHAT)

    # Регистрируем middleware для работы с базой данных
    @dp.update.middleware()
    async def db_session_middleware(handler, event, data):
        async with AsyncSession(engine) as session:
            data["session"] = session

            # Если это сообщение, регистрируем пользователя
            if hasattr(event, "message") and event.message:
                try:
                    await register_user(event.message, session)
                except Exception as e:
                    logger.error(f"Ошибка при регистрации пользователя: {str(e)}")

            return await handler(event, data)

    # Регистрируем хендлеры
    dp.include_router(register_base_handlers())
    dp.include_router(register_registration_handlers())
    dp.include_router(register_receipt_handlers())

    # Регистрируем обработчики запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Запускаем бота
    try:
        logger.info("Запуск бота...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    # Создаем директорию для временных файлов
    os.makedirs("temp", exist_ok=True)

    # Запускаем бота
    asyncio.run(main())
