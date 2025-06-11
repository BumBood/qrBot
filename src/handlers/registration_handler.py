from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_model import User
from logger import logger

# Создаем роутер для регистрации
router = Router()


async def register_user(message: Message, session: AsyncSession) -> User:
    """
    Регистрирует нового пользователя или обновляет данные существующего

    Args:
        message: Сообщение от пользователя
        session: Сессия базы данных

    Returns:
        User: Объект пользователя
    """
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        full_name = message.from_user.full_name

        # Проверяем, существует ли пользователь
        user_query = await session.execute(select(User).where(User.id == user_id))
        user = user_query.scalars().first()

        if user:
            # Обновляем данные существующего пользователя
            user.username = username
            user.full_name = full_name
            logger.info(f"Обновлены данные пользователя: {user_id}")
        else:
            # Создаем нового пользователя
            user = User(id=user_id, username=username, full_name=full_name)
            session.add(user)
            logger.info(f"Зарегистрирован новый пользователь: {user_id}")

        # Сохраняем изменения
        await session.commit()
        return user

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при регистрации пользователя: {str(e)}")
        raise


async def update_user_phone(
    user_id: int, phone_last4: str, session: AsyncSession
) -> bool:
    """
    Обновляет последние 4 цифры телефона пользователя

    Args:
        user_id: ID пользователя
        phone_last4: Последние 4 цифры телефона
        session: Сессия базы данных

    Returns:
        bool: True, если обновление прошло успешно
    """
    try:
        # Проверяем формат телефона
        if not phone_last4.isdigit() or len(phone_last4) != 4:
            logger.error(f"Неверный формат последних 4 цифр телефона: {phone_last4}")
            return False

        # Получаем пользователя
        user_query = await session.execute(select(User).where(User.id == user_id))
        user = user_query.scalars().first()

        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден")
            return False

        # Обновляем телефон
        user.phone_last4 = phone_last4
        await session.commit()

        logger.info(f"Обновлены последние 4 цифры телефона для пользователя {user_id}")
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка при обновлении телефона пользователя: {str(e)}")
        return False


def register_registration_handlers() -> Router:
    """
    Регистрирует хендлеры для регистрации и возвращает роутер
    """
    return router
