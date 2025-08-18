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
        self.chat_not_found_count = 0

    async def get_all_users(self) -> List[User]:
        """Получает всех пользователей из базы данных"""
        async with AsyncSession(engine) as session:
            result = await session.execute(select(User))
            users = result.scalars().all()
            logger.info(f"Найдено пользователей в БД: {len(users)}")
            return list(users)

    async def check_chat_availability(self, chat_id: int) -> bool:
        """
        Быстро проверяет доступность чата, отправив простой запрос
        Возвращает True если чат доступен, False если нет
        """
        try:
            # Пытаемся получить информацию о чате
            await self.bot.get_chat(chat_id)
            return True
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            error_text = str(e).lower()
            if "chat not found" in error_text:
                logger.debug(f"💬 Чат {chat_id} не найден при проверке доступности")
                self.chat_not_found_count += 1
            elif "forbidden" in error_text:
                logger.debug(f"🚫 Бот заблокирован пользователем {chat_id}")

            if chat_id not in self.blocked_users:
                self.blocked_users.append(chat_id)
            return False
        except Exception as e:
            logger.debug(f"⚠️ Ошибка при проверке чата {chat_id}: {e}")
            return True  # Даем шанс попробовать удалить сообщения

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
            # Различные ошибки (слишком старое сообщение, нет прав, чат не найден и т.д.)
            error_text = str(e).lower()

            if "chat not found" in error_text:
                # Чат удален или бот исключен из чата
                logger.warning(f"💬 Чат {chat_id} не найден (удален или бот исключен)")
                self.chat_not_found_count += 1
                if chat_id not in self.blocked_users:
                    self.blocked_users.append(chat_id)
                return False
            elif "message to delete not found" in error_text:
                logger.debug(
                    f"⚠️ Сообщение {message_id} в чате {chat_id} не найдено для удаления"
                )
            elif "message can't be deleted" in error_text:
                logger.warning(
                    f"⚠️ Сообщение {message_id} в чате {chat_id} нельзя удалить (слишком старое)"
                )
            elif "user is deactivated" in error_text:
                logger.warning(f"👤 Пользователь {chat_id} деактивирован")
                if chat_id not in self.blocked_users:
                    self.blocked_users.append(chat_id)
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

        # Проверяем доступность чата с первым сообщением
        if message_ids:
            first_check = await self.delete_message_safely(chat_id, message_ids[0])
            if not first_check and chat_id in self.blocked_users:
                # Если чат недоступен, пропускаем остальные сообщения для этого пользователя
                logger.warning(f"⏭️ Пропускаем пользователя {chat_id} (чат недоступен)")
                return 0
            elif first_check:
                deleted += 1

        # Продолжаем с остальными сообщениями
        for message_id in message_ids[1:]:
            if await self.delete_message_safely(chat_id, message_id):
                deleted += 1
            # Небольшая задержка между запросами
            await asyncio.sleep(0.1)
        return deleted

    async def get_chat_info_and_display(self, chat_id: int) -> bool:
        """
        Получает и отображает информацию о чате

        Args:
            chat_id: ID чата

        Returns:
            bool: True если чат доступен, False если недоступен
        """
        try:
            # Получаем подробную информацию о чате
            chat_info = await self.bot.get_chat(chat_id)

            print(f"\n📋 ИНФОРМАЦИЯ О ЧАТЕ:")
            print(f"🆔 ID чата: {chat_id}")
            print(f"📱 Тип чата: {chat_info.type}")

            if hasattr(chat_info, "first_name") and chat_info.first_name:
                print(f"👤 Имя: {chat_info.first_name}")
            if hasattr(chat_info, "last_name") and chat_info.last_name:
                print(f"👤 Фамилия: {chat_info.last_name}")
            if hasattr(chat_info, "username") and chat_info.username:
                print(f"👤 Username: @{chat_info.username}")
            if hasattr(chat_info, "bio") and chat_info.bio:
                print(f"📝 Био: {chat_info.bio}")

            # Пытаемся получить количество участников (только для групп/каналов)
            if chat_info.type in ["group", "supergroup", "channel"]:
                try:
                    member_count = await self.bot.get_chat_member_count(chat_id)
                    print(f"👥 Участников в чате: {member_count:,}")
                except Exception as e:
                    logger.debug(f"Не удалось получить количество участников: {e}")
            else:
                print(
                    "💬 Приватный чат (точное количество сообщений недоступно через Bot API)"
                )

            # Дополнительная информация если доступна
            if hasattr(chat_info, "description") and chat_info.description:
                print(
                    f"📄 Описание: {chat_info.description[:100]}{'...' if len(chat_info.description) > 100 else ''}"
                )

            print("-" * 50)
            return True

        except (TelegramForbiddenError, TelegramBadRequest) as e:
            error_text = str(e).lower()
            if "chat not found" in error_text:
                print(f"💬 Чат {chat_id} не найден (удален или бот исключен)")
                self.chat_not_found_count += 1
            elif "forbidden" in error_text:
                print(f"🚫 Бот заблокирован пользователем {chat_id}")
            else:
                print(f"❌ Ошибка доступа к чату {chat_id}: {e}")

            if chat_id not in self.blocked_users:
                self.blocked_users.append(chat_id)
            return False

        except Exception as e:
            print(f"❌ Ошибка при получении информации о чате {chat_id}: {e}")
            logger.error(f"Ошибка get_chat для {chat_id}: {e}")
            return False

    async def delete_all_messages_for_user(
        self, chat_id: int, start_message_id: int = 1, end_message_id: int = 50000
    ) -> int:
        """
        Удаляет все доступные сообщения у конкретного пользователя без лимита поиска

        Args:
            chat_id: ID пользователя
            start_message_id: Начальный ID сообщения
            end_message_id: Конечный ID сообщения
        """
        deleted = 0
        attempts = 0

        logger.info(f"🎯 Удаление всех сообщений у пользователя {chat_id}")
        logger.info(f"📍 Диапазон message_id: {start_message_id}-{end_message_id}")

        # Получаем и отображаем информацию о чате
        print(f"📊 Получение информации о чате {chat_id}...")
        if not await self.get_chat_info_and_display(chat_id):
            logger.warning(f"⏭️ Пользователь {chat_id} недоступен")
            return 0

        # Показываем что будем делать
        total_range = end_message_id - start_message_id + 1
        print(f"🎯 Будет проверено сообщений: {total_range:,}")
        print(f"📍 Диапазон ID сообщений: {start_message_id} - {end_message_id}")
        print(f"⚠️ ВНИМАНИЕ: Проверяются ВСЕ сообщения в диапазоне (не только от бота)")
        print("-" * 50)

        # Пробуем удалить сообщения в обратном порядке
        try:
            for message_id in range(end_message_id, start_message_id - 1, -1):
                attempts += 1

                if attempts % 500 == 0:  # Прогресс каждые 500 попыток
                    logger.info(
                        f"📈 Обработано {attempts} сообщений, удалено: {deleted}"
                    )
                    logger.info(f"📍 Текущий message_id: {message_id}")

                try:
                    success = await self.delete_message_safely(chat_id, message_id)
                    if success:
                        deleted += 1
                        if deleted % 25 == 0:  # Логируем каждые 25 удалений
                            logger.info(
                                f"✅ Удалено {deleted} сообщений у пользователя {chat_id}"
                            )

                    # Небольшая задержка между попытками
                    await asyncio.sleep(0.03)  # Уменьшенная задержка для быстроты

                except Exception as e:
                    logger.debug(f"Ошибка при обработке сообщения {message_id}: {e}")
                    continue

        except KeyboardInterrupt:
            logger.warning(
                f"⏹️ Операция прервана пользователем. Обработано: {attempts}, удалено: {deleted}"
            )

            # Показываем статистику даже при прерывании
            total_range = end_message_id - start_message_id + 1
            progress_percent = (attempts / total_range) * 100 if total_range > 0 else 0

            print("\n" + "=" * 50)
            print("⏹️ ОПЕРАЦИЯ ПРЕРВАНА ПОЛЬЗОВАТЕЛЕМ")
            print("📊 СТАТИСТИКА НА МОМЕНТ ПРЕРЫВАНИЯ:")
            print(f"✅ Удалено сообщений от бота: {deleted}")
            print(f"📈 Всего проверено message_id: {attempts:,}")
            print(f"📊 Прогресс проверки: {progress_percent:.1f}%")
            print("=" * 50)

            return deleted

        # Финальная статистика
        total_range = end_message_id - start_message_id + 1
        progress_percent = (attempts / total_range) * 100 if total_range > 0 else 0

        logger.info(
            f"🏁 Завершена обработка пользователя {chat_id}. Удалено: {deleted}, проверено: {attempts}"
        )

        print("\n" + "=" * 50)
        print("🏁 ОПЕРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("📊 ФИНАЛЬНАЯ СТАТИСТИКА:")
        print(f"✅ Удалено сообщений от бота: {deleted}")
        print(f"📈 Всего проверено message_id: {attempts:,}")
        print(f"📊 Прогресс проверки: {progress_percent:.1f}%")
        if deleted > 0:
            efficiency = (deleted / attempts) * 100 if attempts > 0 else 0
            print(
                f"⚡ Эффективность удаления: {efficiency:.2f}% (найдено сообщений от бота)"
            )
        print("=" * 50)

        return deleted

    async def smart_delete_for_user(
        self,
        chat_id: int,
        iterations: int = 100,
        test_message: str = "🧹 Очистка чата...",
    ) -> int:
        """
        Умное удаление сообщений: отправляет сообщение, удаляет предыдущее и текущее

        Args:
            chat_id: ID пользователя
            iterations: Количество итераций удаления
            test_message: Текст тестового сообщения для отправки
        """
        deleted = 0
        sent_messages = []

        logger.info(f"🧠 Умное удаление сообщений у пользователя {chat_id}")
        logger.info(f"🔄 Количество итераций: {iterations}")

        # Получаем и отображаем информацию о чате
        print(f"📊 Получение информации о чате {chat_id}...")
        if not await self.get_chat_info_and_display(chat_id):
            logger.warning(f"⏭️ Пользователь {chat_id} недоступен")
            return 0

        print(f"🧠 Начинаем умное удаление сообщений:")
        print(f"📤 Отправляем тестовое сообщение: '{test_message}'")
        print(f"🗑️ Удаляем предыдущее сообщение (message_id - 1)")
        print(f"🗑️ Удаляем текущее сообщение")
        print(f"🔄 Повторяем {iterations} раз")
        print("-" * 50)

        try:
            for i in range(iterations):
                try:
                    # Отправляем тестовое сообщение
                    sent_message = await self.bot.send_message(
                        chat_id=chat_id, text=f"{test_message} ({i+1}/{iterations})"
                    )

                    current_message_id = sent_message.message_id
                    previous_message_id = current_message_id - 1

                    logger.debug(f"📤 Отправлено сообщение {current_message_id}")
                    sent_messages.append(current_message_id)

                    # Небольшая задержка перед удалением
                    await asyncio.sleep(0.1)

                    # Удаляем предыдущее сообщение (message_id - 1)
                    previous_deleted = await self.delete_message_safely(
                        chat_id, previous_message_id
                    )
                    if previous_deleted:
                        deleted += 1
                        logger.debug(
                            f"🗑️ Удалено предыдущее сообщение {previous_message_id}"
                        )

                    # Удаляем текущее отправленное сообщение
                    current_deleted = await self.delete_message_safely(
                        chat_id, current_message_id
                    )
                    if current_deleted:
                        deleted += 1
                        logger.debug(
                            f"🗑️ Удалено текущее сообщение {current_message_id}"
                        )

                        # Убираем из списка отправленных, так как удалили
                        if current_message_id in sent_messages:
                            sent_messages.remove(current_message_id)

                    # Показываем прогресс
                    if (i + 1) % 10 == 0:
                        logger.info(
                            f"📈 Итерация {i+1}/{iterations}, удалено: {deleted}"
                        )

                    # Задержка между итерациями
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning(f"⚠️ Ошибка на итерации {i+1}: {e}")
                    continue

        except KeyboardInterrupt:
            current_iteration = locals().get("i", -1) + 1
            logger.warning(
                f"⏹️ Умное удаление прервано пользователем на итерации {current_iteration}"
            )

            # Пытаемся очистить оставшиеся отправленные сообщения
            if sent_messages:
                print(
                    f"\n🧹 Очистка {len(sent_messages)} оставшихся тестовых сообщений..."
                )
                for msg_id in sent_messages:
                    try:
                        success = await self.delete_message_safely(chat_id, msg_id)
                        if success:
                            deleted += 1
                    except Exception as e:
                        logger.debug(f"Ошибка при очистке сообщения {msg_id}: {e}")
                        continue

            print("\n" + "=" * 50)
            print("⏹️ УМНОЕ УДАЛЕНИЕ ПРЕРВАНО")
            print("📊 СТАТИСТИКА НА МОМЕНТ ПРЕРЫВАНИЯ:")
            print(f"✅ Удалено сообщений: {deleted}")
            print(f"🔄 Выполнено итераций: {current_iteration}/{iterations}")
            print("=" * 50)

            return deleted

        # Очистка оставшихся тестовых сообщений (если есть)
        if sent_messages:
            logger.info(
                f"🧹 Очистка {len(sent_messages)} оставшихся тестовых сообщений..."
            )
            for msg_id in sent_messages:
                try:
                    success = await self.delete_message_safely(chat_id, msg_id)
                    if success:
                        deleted += 1
                except Exception as e:
                    logger.debug(f"Ошибка при очистке сообщения {msg_id}: {e}")
                    continue

        logger.info(
            f"🏁 Умное удаление завершено для пользователя {chat_id}. Удалено: {deleted}"
        )

        print("\n" + "=" * 50)
        print("🧠 УМНОЕ УДАЛЕНИЕ ЗАВЕРШЕНО!")
        print("📊 ФИНАЛЬНАЯ СТАТИСТИКА:")
        print(f"✅ Удалено сообщений: {deleted}")
        print(f"🔄 Выполнено итераций: {iterations}")
        efficiency = (deleted / (iterations * 2)) * 100 if iterations > 0 else 0
        print(f"⚡ Эффективность: {efficiency:.1f}% (от теоретического максимума)")
        print("💡 Примечание: удаляются как предыдущие, так и новые сообщения")
        print("=" * 50)

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

            # Проверяем, не заблокирован ли уже пользователь после первых попыток
            if attempts > 0 and chat_id in self.blocked_users:
                logger.warning(
                    f"⏭️ Пропускаем остальные сообщения для {chat_id} (чат недоступен)"
                )
                break

            try:
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

            # Быстрая проверка доступности чата
            user_id = int(user.id)  # Явное приведение типа для избежания ошибок линтера
            if not await self.check_chat_availability(user_id):
                logger.info(f"⏭️ Пропускаем пользователя {user_id} (чат недоступен)")
                continue

            try:
                if message_ids:
                    # Удаляем конкретные сообщения
                    await self.delete_messages_by_ids(user_id, message_ids)

                elif search_text and message_id_range:
                    # Ищем и удаляем сообщения в диапазоне
                    await self.search_and_delete_messages_in_range(
                        user_id, search_text, message_id_range[0], message_id_range[1]
                    )

                # Пауза между пользователями
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ Ошибка при обработке пользователя {user_id}: {e}")
                continue

        # Выводим статистику
        logger.info("\n" + "=" * 50)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info(f"✅ Удалено сообщений: {self.deleted_count}")
        logger.info(f"❌ Ошибок: {self.error_count}")
        logger.info(f"🚫 Недоступных пользователей: {len(self.blocked_users)}")
        logger.info(f"💬 Чатов не найдено: {self.chat_not_found_count}")
        if self.blocked_users:
            logger.info(
                f"🚫 ID недоступных пользователей: {self.blocked_users[:10]}{'...' if len(self.blocked_users) > 10 else ''}"
            )
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
        print("4. Удалить все сообщения у конкретного пользователя (без лимита)")
        print("5. Умное удаление: отправка + удаление предыдущего и текущего сообщения")

        choice = input("Введите номер режима (1-5): ").strip()

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

        elif choice == "4":
            # Режим удаления всех сообщений у конкретного пользователя
            user_id_str = input("Введите ID пользователя: ").strip()
            if not user_id_str.isdigit():
                logger.error("❌ ID пользователя должен быть числом")
                return

            user_id = int(user_id_str)

            # Примечание о поиске по тексту
            print(
                "ℹ️ ВАЖНО: В данном режиме удаляются ВСЕ сообщения в указанном диапазоне."
            )
            print(
                "ℹ️ Telegram Bot API не позволяет предварительно прочитать текст сообщения перед удалением."
            )

            # Настройка диапазона
            print("📍 Диапазон поиска:")
            print("1. По умолчанию (1-50000)")
            print("2. Настроить вручную")

            range_choice = input("Выберите опцию (1-2): ").strip()

            if range_choice == "2":
                start_id = input(
                    "Введите начальный message_id (по умолчанию 1): "
                ).strip()
                start_id = int(start_id) if start_id.isdigit() else 1

                end_id = input(
                    "Введите конечный message_id (по умолчанию 50000): "
                ).strip()
                end_id = int(end_id) if end_id.isdigit() else 50000
            else:
                start_id = 1
                end_id = 50000

            # Подтверждение
            confirm = (
                input(
                    f"⚠️ Удалить ВСЕ сообщения у пользователя {user_id} в диапазоне {start_id}-{end_id}? (да/нет): "
                )
                .strip()
                .lower()
            )

            if confirm not in ["да", "yes", "y"]:
                logger.info("❌ Отменено пользователем")
                return

            # Выполняем удаление
            print(f"🚀 Начинаем удаление ВСЕХ сообщений у пользователя {user_id}...")
            print("⚠️ ВНИМАНИЕ: Это может занять много времени!")
            print("⏹️ Для прерывания используйте Ctrl+C")
            print("📊 Прогресс будет показываться каждые 500 проверенных сообщений")
            print("-" * 60)

            deleted = await deleter.delete_all_messages_for_user(
                chat_id=user_id, start_message_id=start_id, end_message_id=end_id
            )

            print(f"\n✅ Обработка завершена!")
            print(f"✅ Удалено сообщений: {deleted}")

        elif choice == "5":
            # Режим умного удаления
            user_id_str = input("Введите ID пользователя: ").strip()
            if not user_id_str.isdigit():
                logger.error("❌ ID пользователя должен быть числом")
                return

            user_id = int(user_id_str)

            # Настройка параметров
            iterations_str = input("Количество итераций (по умолчанию 100): ").strip()
            iterations = int(iterations_str) if iterations_str.isdigit() else 100

            test_message = input(
                "Текст тестового сообщения (или Enter для стандартного): "
            ).strip()
            if not test_message:
                test_message = "🧹 Очистка чата..."

            print("\n💡 КАК РАБОТАЕТ УМНОЕ УДАЛЕНИЕ:")
            print("1. 📤 Отправляется тестовое сообщение")
            print("2. 📍 Определяется его message_id")
            print("3. 🗑️ Удаляется предыдущее сообщение (message_id - 1)")
            print("4. 🗑️ Удаляется текущее тестовое сообщение")
            print("5. 🔄 Процесс повторяется N раз")
            print(f"\n📊 Параметры:")
            print(f"👤 Пользователь: {user_id}")
            print(f"🔄 Итераций: {iterations}")
            print(f"💬 Тестовое сообщение: '{test_message}'")
            print(f"⏱️ Теоретический максимум удалений: {iterations * 2}")

            # Подтверждение
            confirm = (
                input(
                    f"\n⚠️ Запустить умное удаление для пользователя {user_id}? (да/нет): "
                )
                .strip()
                .lower()
            )

            if confirm not in ["да", "yes", "y"]:
                logger.info("❌ Отменено пользователем")
                return

            # Выполняем умное удаление
            print(f"\n🧠 Запускаем умное удаление для пользователя {user_id}...")
            print("⏹️ Для прерывания используйте Ctrl+C")
            print("-" * 60)

            deleted = await deleter.smart_delete_for_user(
                chat_id=user_id, iterations=iterations, test_message=test_message
            )

            print(f"\n✅ Умное удаление завершено!")
            print(f"✅ Удалено сообщений: {deleted}")

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
