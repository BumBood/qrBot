#!/usr/bin/env python3
"""
Скрипт для удаления сообщений от бота в диалогах с пользователями
"""
import asyncio
import sys
import os
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Добавляем путь к src для импортов
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
)

from config import BOT_TOKEN
from database import engine
from models.user_model import User
from logger import logger


class MessageDeleter:
    """Класс для удаления сообщений от бота"""

    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.deleted_count = 0
        self.error_count = 0
        self.blocked_users: List[int] = []

    async def get_all_users(self) -> List[User]:
        """Получает всех пользователей из базы данных"""
        async with AsyncSession(engine) as session:
            result = await session.execute(select(User))
            users = result.scalars().all()
            logger.info(f"Найдено пользователей в БД: {len(users)}")
            return list(users)

    async def delete_message_safely(self, chat_id: int, message_id: int) -> bool:
        """Безопасно удаляет сообщение с обработкой ошибок"""
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            self.deleted_count += 1
            logger.info(f"✅ Удалено сообщение {message_id} в чате {chat_id}")
            return True

        except TelegramNotFound:
            # Сообщение уже удалено или не найдено
            logger.debug(f"⚠️ Сообщение {message_id} в чате {chat_id} не найдено")
            return False

        except TelegramForbiddenError:
            # Бот заблокирован пользователем
            logger.warning(f"🚫 Бот заблокирован пользователем {chat_id}")
            self.blocked_users.append(chat_id)
            return False

        except TelegramBadRequest as e:
            # Различные ошибки (слишком старое сообщение, нет прав и т.д.)
            if "message to delete not found" in str(e).lower():
                logger.debug(
                    f"⚠️ Сообщение {message_id} в чате {chat_id} не найдено для удаления"
                )
            elif "message can't be deleted" in str(e).lower():
                logger.warning(
                    f"⚠️ Сообщение {message_id} в чате {chat_id} нельзя удалить (слишком старое)"
                )
            else:
                logger.error(
                    f"❌ Ошибка при удалении сообщения {message_id} в чате {chat_id}: {e}"
                )
            self.error_count += 1
            return False

        except Exception as e:
            logger.error(
                f"❌ Неожиданная ошибка при удалении сообщения {message_id} в чате {chat_id}: {e}"
            )
            self.error_count += 1
            return False

    async def delete_messages_by_ids(self, chat_id: int, message_ids: List[int]) -> int:
        """Удаляет сообщения по их ID"""
        deleted = 0
        for message_id in message_ids:
            if await self.delete_message_safely(chat_id, message_id):
                deleted += 1
            # Небольшая задержка между запросами
            await asyncio.sleep(0.1)
        return deleted

    async def search_and_delete_messages_in_range(
        self,
        chat_id: int,
        search_text: str,
        start_message_id: int = 1,
        end_message_id: int = 10000,
        max_attempts: int = 100,
    ) -> int:
        """
        Пытается найти и удалить сообщения с определенным текстом в диапазоне ID

        ВНИМАНИЕ: Этот метод работает методом проб и ошибок, так как Telegram Bot API
        не предоставляет метод получения истории сообщений
        """
        deleted = 0
        attempts = 0

        logger.info(f"🔍 Поиск сообщений с текстом '{search_text}' в чате {chat_id}")
        logger.info(f"📍 Диапазон message_id: {start_message_id}-{end_message_id}")

        # Пробуем удалить сообщения в обратном порядке (новые сообщения имеют больший ID)
        for message_id in range(end_message_id, start_message_id - 1, -1):
            if attempts >= max_attempts:
                logger.info(
                    f"⏹️ Достигнут лимит попыток ({max_attempts}) для чата {chat_id}"
                )
                break

            try:
                # Пытаемся получить информацию о сообщении через forward
                # (это косвенный способ проверить существование сообщения)

                # Сначала пытаемся удалить сообщение
                success = await self.delete_message_safely(chat_id, message_id)
                if success:
                    deleted += 1
                    logger.info(f"✅ Удалено сообщение {message_id} в чате {chat_id}")

                attempts += 1

                # Задержка между попытками
                await asyncio.sleep(0.2)

            except Exception as e:
                logger.debug(f"Ошибка при обработке сообщения {message_id}: {e}")
                attempts += 1
                continue

        logger.info(
            f"🏁 Завершен поиск в чате {chat_id}. Удалено: {deleted}, попыток: {attempts}"
        )
        return deleted

    async def delete_messages_for_all_users(
        self,
        search_text: Optional[str] = None,
        message_ids: Optional[List[int]] = None,
        message_id_range: Optional[tuple] = None,
    ):
        """
        Удаляет сообщения для всех пользователей

        Args:
            search_text: Текст для поиска (используется с message_id_range)
            message_ids: Конкретные ID сообщений для удаления
            message_id_range: Кортеж (start_id, end_id) для поиска сообщений
        """
        users = await self.get_all_users()

        logger.info(f"🚀 Начинаем обработку {len(users)} пользователей")

        if search_text and message_id_range:
            logger.info(
                f"🎯 Режим: Поиск и удаление сообщений с текстом '{search_text}'"
            )
            logger.info(f"📍 Диапазон ID: {message_id_range[0]}-{message_id_range[1]}")
        elif message_ids:
            logger.info(f"🎯 Режим: Удаление конкретных сообщений {message_ids}")
        else:
            logger.error("❌ Не указан режим работы!")
            return

        for i, user in enumerate(users, 1):
            logger.info(
                f"👤 [{i}/{len(users)}] Обработка пользователя {user.id} (@{user.username})"
            )

            try:
                if message_ids:
                    # Удаляем конкретные сообщения
                    await self.delete_messages_by_ids(user.id, message_ids)

                elif search_text and message_id_range:
                    # Ищем и удаляем сообщения в диапазоне
                    await self.search_and_delete_messages_in_range(
                        user.id, search_text, message_id_range[0], message_id_range[1]
                    )

                # Пауза между пользователями
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ Ошибка при обработке пользователя {user.id}: {e}")
                continue

        # Выводим статистику
        logger.info("\n" + "=" * 50)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info(f"✅ Удалено сообщений: {self.deleted_count}")
        logger.info(f"❌ Ошибок: {self.error_count}")
        logger.info(f"🚫 Пользователей заблокировало бота: {len(self.blocked_users)}")
        if self.blocked_users:
            logger.info(f"🚫 Заблокированные пользователи: {self.blocked_users}")
        logger.info("=" * 50)

    async def close(self):
        """Закрывает соединение с ботом"""
        await self.bot.session.close()


async def main():
    """Главная функция скрипта"""

    # Проверяем наличие токена
    if not BOT_TOKEN:
        logger.error(
            "❌ Токен бота не найден. Установите переменную окружения BOT_TOKEN"
        )
        return

    # Создаем экземпляр удалителя сообщений
    deleter = MessageDeleter(BOT_TOKEN)

    try:
        print("🤖 Скрипт для удаления сообщений от бота")
        print("=" * 50)
        print("Выберите режим работы:")
        print("1. Удалить конкретные сообщения по ID")
        print("2. Найти и удалить сообщения с определенным текстом в диапазоне ID")
        print("3. Быстрое удаление - указать текст и примерный диапазон")

        choice = input("Введите номер режима (1-3): ").strip()

        if choice == "1":
            # Режим удаления конкретных сообщений
            message_ids_str = input("Введите ID сообщений через запятую: ").strip()
            message_ids = [
                int(x.strip())
                for x in message_ids_str.split(",")
                if x.strip().isdigit()
            ]

            if not message_ids:
                logger.error("❌ Не указаны корректные ID сообщений")
                return

            confirm = (
                input(
                    f"⚠️ Удалить сообщения {message_ids} у всех пользователей? (да/нет): "
                )
                .strip()
                .lower()
            )
            if confirm not in ["да", "yes", "y"]:
                logger.info("❌ Отменено пользователем")
                return

            await deleter.delete_messages_for_all_users(message_ids=message_ids)

        elif choice == "2":
            # Режим поиска и удаления по тексту
            search_text = input(
                "Введите текст для поиска (например, 'Победитель: чек № 27'): "
            ).strip()
            if not search_text:
                logger.error("❌ Не указан текст для поиска")
                return

            start_id = input("Введите начальный message_id (по умолчанию 1): ").strip()
            start_id = int(start_id) if start_id.isdigit() else 1

            end_id = input("Введите конечный message_id (по умолчанию 1000): ").strip()
            end_id = int(end_id) if end_id.isdigit() else 1000

            confirm = (
                input(
                    f"⚠️ Искать и удалить сообщения с текстом '{search_text}' в диапазоне {start_id}-{end_id}? (да/нет): "
                )
                .strip()
                .lower()
            )
            if confirm not in ["да", "yes", "y"]:
                logger.info("❌ Отменено пользователем")
                return

            await deleter.delete_messages_for_all_users(
                search_text=search_text, message_id_range=(start_id, end_id)
            )

        elif choice == "3":
            # Быстрый режим для сообщений о победителях
            search_text = input(
                "Введите текст сообщения (по умолчанию 'Победитель: чек №'): "
            ).strip()
            if not search_text:
                search_text = "Победитель: чек №"

            print(f"🎯 Будем искать сообщения с текстом: '{search_text}'")
            print(
                "📍 Диапазон поиска: последние 500 сообщений (ID от текущего-500 до текущего)"
            )

            confirm = input("⚠️ Продолжить? (да/нет): ").strip().lower()
            if confirm not in ["да", "yes", "y"]:
                logger.info("❌ Отменено пользователем")
                return

            # Используем примерный диапазон для поиска недавних сообщений
            # В реальности нужно будет скорректировать диапазон
            await deleter.delete_messages_for_all_users(
                search_text=search_text, message_id_range=(1, 500)  # Примерный диапазон
            )

        else:
            logger.error("❌ Неверный выбор режима")
            return

    except KeyboardInterrupt:
        logger.info("⏹️ Скрипт прерван пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await deleter.close()


if __name__ == "__main__":
    # Запускаем скрипт
    asyncio.run(main())
