import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.weekly_lottery_model import WeeklyLottery
from models.receipt_model import Receipt
from models.user_model import User
from logger import logger
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path

# Определяем корневую директорию проекта для абсолютных путей
BASE_DIR = Path(__file__).resolve().parents[2]

# Убрана проверка аптек: остаётся только наличие товаров «Айсида»


class WeeklyLotteryService:
    """Сервис для еженедельного розыгрыша сертификатов OZON на 5000 руб"""

    @staticmethod
    def get_previous_week_dates() -> tuple[datetime, datetime]:
        """
        Возвращает даты начала и конца предыдущей недели

        Returns:
            tuple: (понедельник 00:00, воскресенье 23:59) предыдущей недели
        """
        today = datetime.now()
        # Находим понедельник текущей недели
        current_monday = today - timedelta(days=today.weekday())
        current_monday = current_monday.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Предыдущий понедельник (начало предыдущей недели)
        prev_monday = current_monday - timedelta(days=7)

        # Предыдущее воскресенье (конец предыдущей недели)
        prev_sunday = prev_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

        return prev_monday, prev_sunday

    @staticmethod
    def get_current_week_dates() -> tuple[datetime, datetime]:
        """
        Возвращает даты начала и конца текущей недели
        """
        today = datetime.now()
        # Находим понедельник текущей недели
        current_monday = today - timedelta(days=today.weekday())
        current_monday = current_monday.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Текущее воскресенье (конец недели)
        current_sunday = current_monday + timedelta(
            days=6, hours=23, minutes=59, seconds=59
        )

        return current_monday, current_sunday

    @staticmethod
    async def get_eligible_receipts(
        session: AsyncSession, week_start: datetime, week_end: datetime
    ) -> list[Receipt]:
        """
        Получает все подтверждённые чеки за указанную неделю

        Args:
            session: Сессия базы данных
            week_start: Начало недели
            week_end: Конец недели

        Returns:
            list[Receipt]: Список подходящих чеков
        """
        try:
            # Получаем все подтверждённые чеки за неделю
            query = await session.execute(
                select(Receipt).where(
                    and_(
                        Receipt.status == "verified",
                        Receipt.created_at >= week_start,
                        Receipt.created_at <= week_end,
                    )
                )
            )
            receipts = query.scalars().all()
            logger.info(
                f"Найдено {len(receipts)} подтверждённых чеков "
                f"с {week_start.strftime('%d.%m.%Y')} по {week_end.strftime('%d.%m.%Y')}"
            )
            # Фильтруем по наличию продукции «Айсида»
            eligible = [r for r in receipts if r.items_count > 0]
            logger.info(
                f"После фильтрации осталось {len(eligible)} подходящих чеков для розыгрыша"
            )
            return eligible

        except Exception as e:
            logger.error(f"Ошибка при получении подходящих чеков: {str(e)}")
            return []

    @staticmethod
    async def conduct_lottery(
        session: AsyncSession, bot=None, *, for_current_week: bool = False
    ) -> Dict[str, Any]:
        """
        Проводит еженедельный розыгрыш

        Args:
            session: Сессия базы данных
            bot: Экземпляр бота для отправки уведомлений
            for_current_week: Флаг, указывающий на тип недели для розыгрыша

        Returns:
            Dict[str, Any]: Результат розыгрыша
        """
        try:
            # Выбираем даты в зависимости от типа лотереи
            if for_current_week:
                week_start, week_end = WeeklyLotteryService.get_current_week_dates()
                logger.info(
                    f"Проводим розыгрыш за текущую неделю {week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}"
                )
            else:
                week_start, week_end = WeeklyLotteryService.get_previous_week_dates()
                logger.info(
                    f"Проводим розыгрыш за предыдущую неделю {week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}"
                )

            # Проверяем, не проводился ли уже розыгрыш за эту неделю
            existing_lottery = await session.execute(
                select(WeeklyLottery).where(
                    and_(
                        WeeklyLottery.week_start == week_start,
                        WeeklyLottery.week_end == week_end,
                    )
                )
            )

            if existing_lottery.scalars().first():
                logger.warning(
                    f"Розыгрыш за неделю {week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')} уже проводился"
                )
                return {
                    "success": False,
                    "error": "Розыгрыш за эту неделю уже проводился",
                }

            # Получаем подходящие чеки
            eligible_receipts = await WeeklyLotteryService.get_eligible_receipts(
                session, week_start, week_end
            )

            if not eligible_receipts:
                logger.info("Нет подходящих чеков для розыгрыша")

                # Создаём запись о розыгрыше без победителя
                lottery_record = WeeklyLottery(
                    week_start=week_start,
                    week_end=week_end,
                    conducted_at=datetime.now(),
                )

                session.add(lottery_record)
                await session.commit()

                return {
                    "success": True,
                    "winner": None,
                    "participants_count": 0,
                    "message": "Нет участников для розыгрыша",
                }

            # Выбираем случайный чек
            winner_receipt = random.choice(eligible_receipts)

            # Создаём запись о розыгрыше
            lottery_record = WeeklyLottery(
                week_start=week_start,
                week_end=week_end,
                winner_user_id=winner_receipt.user_id,
                winner_receipt_id=winner_receipt.id,
                conducted_at=datetime.now(),
            )

            session.add(lottery_record)
            await session.commit()
            await session.refresh(lottery_record)

            # Отправляем уведомление победителю
            notification_sent = False
            if bot:
                notification_sent = await WeeklyLotteryService.notify_winner(
                    session, bot, lottery_record
                )

                # Обновляем статус уведомления
                lottery_record.notification_sent = notification_sent
                await session.commit()

            logger.info(
                f"Розыгрыш проведён! Победитель: пользователь {winner_receipt.user_id}, "
                f"чек {winner_receipt.id}, уведомление отправлено: {notification_sent}"
            )

            return {
                "success": True,
                "winner": {
                    "user_id": winner_receipt.user_id,
                    "receipt_id": winner_receipt.id,
                    "lottery_id": lottery_record.id,
                },
                "participants_count": len(eligible_receipts),
                "notification_sent": notification_sent,
            }

        except Exception as e:
            logger.error(f"Ошибка при проведении еженедельного розыгрыша: {str(e)}")
            try:
                await session.rollback()
            except Exception:
                pass

            return {
                "success": False,
                "error": f"Ошибка при проведении розыгрыша: {str(e)}",
            }

    @staticmethod
    async def notify_winner(
        session: AsyncSession, bot, lottery_record: WeeklyLottery
    ) -> bool:
        """
        Отправляет уведомление победителю еженедельного розыгрыша

        Args:
            session: Сессия базы данных
            bot: Экземпляр бота
            lottery_record: Запись о розыгрыше

        Returns:
            bool: True если уведомление отправлено успешно
        """
        try:
            if not lottery_record.winner_user_id:
                return False

            # Получаем информацию о пользователе
            user_query = await session.execute(
                select(User).where(User.id == lottery_record.winner_user_id)
            )
            user = user_query.scalars().first()

            if not user:
                logger.error(f"Пользователь {lottery_record.winner_user_id} не найден")
                return False

            # Формируем сообщение
            message = (
                "🎉 Поздравляем! \n"
                "Вы выиграли сертификат OZON на 5 000 руб. \n"
                "📞 Пожалуйста, пришлите номер вашего телефона текстом для связи."
            )

            # Отправляем картинку победителю
            # Используем абсолютный путь к файлу картинки
            photo_path = BASE_DIR / "data" / "pics" / "victory.png"
            photo = FSInputFile(str(photo_path))
            # Кнопка для запроса контакта
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Отправить контакт",
                            callback_data=f"send_contact:{lottery_record.id}",
                        )
                    ]
                ]
            )
            await bot.send_photo(
                lottery_record.winner_user_id,
                photo=photo,
                caption=message,
                reply_markup=markup,
            )

            logger.info(
                f"Уведомление о победе отправлено пользователю {lottery_record.winner_user_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления победителю: {str(e)}")
            return False

    @staticmethod
    async def manual_select_winner(
        session: AsyncSession, lottery_id: int, receipt_id: int
    ) -> Dict[str, Any]:
        """
        Ручной выбор победителя розыгрыша

        Args:
            session: Сессия базы данных
            lottery_id: ID розыгрыша
            receipt_id: ID выбранного чека

        Returns:
            Dict[str, Any]: Результат операции
        """
        try:
            # Получаем розыгрыш
            lottery = await session.get(WeeklyLottery, lottery_id)
            if not lottery:
                return {
                    "success": False,
                    "error": f"Розыгрыш с ID {lottery_id} не найден",
                }

            # Проверяем, что розыгрыш ещё не подтверждён
            if lottery.notification_sent:
                return {
                    "success": False,
                    "error": "Нельзя изменить победителя после подтверждения розыгрыша",
                }

            # Получаем выбранный чек
            receipt = await session.get(Receipt, receipt_id)
            if not receipt:
                return {"success": False, "error": f"Чек с ID {receipt_id} не найден"}

            # Проверяем, что чек подходит для этой недели
            if not (lottery.week_start <= receipt.created_at <= lottery.week_end):
                return {
                    "success": False,
                    "error": f"Чек #{receipt_id} не относится к неделе розыгрыша",
                }

            # Проверяем, что чек подтверждён и содержит товары Айсида
            if receipt.status != "verified" or receipt.items_count == 0:
                return {
                    "success": False,
                    "error": f"Чек #{receipt_id} не подходит для розыгрыша (не подтверждён или нет товаров Айсида)",
                }

            # Обновляем победителя
            lottery.winner_user_id = receipt.user_id
            lottery.winner_receipt_id = receipt.id
            await session.commit()

            logger.info(
                f"Ручной выбор победителя: розыгрыш {lottery_id}, "
                f"новый победитель - пользователь {receipt.user_id}, чек {receipt.id}"
            )

            return {
                "success": True,
                "message": f"Победитель изменён на пользователя #{receipt.user_id}, чек #{receipt.id}",
                "winner": {
                    "user_id": receipt.user_id,
                    "receipt_id": receipt.id,
                    "lottery_id": lottery.id,
                },
            }

        except Exception as e:
            logger.error(f"Ошибка при ручном выборе победителя: {str(e)}")
            try:
                await session.rollback()
            except Exception:
                pass

            return {
                "success": False,
                "error": f"Ошибка при выборе победителя: {str(e)}",
            }

    @staticmethod
    async def get_lottery_history(
        session: AsyncSession, limit: int = 10
    ) -> list[WeeklyLottery]:
        """
        Получает историю еженедельных розыгрышей

        Args:
            session: Сессия базы данных
            limit: Количество записей

        Returns:
            list[WeeklyLottery]: Список розыгрышей
        """
        try:
            query = await session.execute(
                select(WeeklyLottery)
                .order_by(WeeklyLottery.created_at.desc())
                .limit(limit)
            )

            return query.scalars().all()

        except Exception as e:
            logger.error(f"Ошибка при получении истории розыгрышей: {str(e)}")
            return []


# Экземпляр сервиса
weekly_lottery_service = WeeklyLotteryService()
