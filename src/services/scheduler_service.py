import asyncio
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.weekly_lottery_service import weekly_lottery_service
from services.google_sheets_service import google_sheets_service
from database import async_session
from logger import logger
from sqlalchemy import select, and_
from models.weekly_lottery_model import WeeklyLottery


class LotteryScheduler:
    """Планировщик для автоматического проведения еженедельных розыгрышей"""

    def __init__(self, bot=None):
        self.scheduler = AsyncIOScheduler()
        self.bot = bot
        self.is_running = False

    async def conduct_weekly_lottery_job(self):
        """Задача для проведения еженедельного розыгрыша"""
        try:
            logger.info("Запуск автоматического еженедельного розыгрыша")

            async with async_session() as session:
                # Проводим розыгрыш без отправки уведомлений, администратор подтвердит вручную
                result = await weekly_lottery_service.conduct_lottery(session)

                if result["success"]:
                    if result.get("winner"):
                        logger.info(
                            f"Еженедельный розыгрыш завершён успешно. "
                            f"Победитель: пользователь {result['winner']['user_id']}, "
                            f"участников: {result['participants_count']}"
                        )
                    else:
                        logger.info(
                            f"Еженедельный розыгрыш завершён, но участников не было"
                        )
                else:
                    logger.error(
                        f"Ошибка при проведении еженедельного розыгрыша: {result.get('error')}"
                    )

        except Exception as e:
            logger.error(
                f"Критическая ошибка в задаче еженедельного розыгрыша: {str(e)}"
            )

    async def export_users_to_sheets_job(self):
        """Задача выгрузки пользователей в Google Sheets"""
        try:
            logger.info("Запуск задачи экспорта пользователей в Google Sheets")
            # Запускаем синхронную выгрузку в пуле
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, google_sheets_service.export_users
            )
            if result.get("success"):
                logger.info(
                    f"Экспорт пользователей завершён, выгружено: {result.get('count')}"
                )
            else:
                logger.error(
                    f"Экспорт пользователей не выполнен: {result.get('error')}"
                )
        except Exception as e:
            logger.error(f"Критическая ошибка экспорта в Google Sheets: {str(e)}")

    async def send_contact_reminders_job(self):
        """Задача для напоминания пользователям о предоставлении контактных данных победителям"""
        logger.info(
            "Запуск задачи напоминания о предоставлении контактных данных победителям"
        )
        try:
            async with async_session() as session:
                # Вычисляем дату ровно один день назад
                threshold = datetime.now() - timedelta(days=1)
                reminder_date = threshold.date()
                # Определяем границы дня (00:00 – 23:59:59)
                from datetime import time

                day_start = datetime.combine(reminder_date, time.min)
                day_end = datetime.combine(reminder_date, time.max)
                result = await session.execute(
                    select(WeeklyLottery).where(
                        and_(
                            WeeklyLottery.winner_user_id != None,
                            WeeklyLottery.notification_sent == True,
                            WeeklyLottery.contact_sent == False,
                            WeeklyLottery.conducted_at >= day_start,
                            WeeklyLottery.conducted_at <= day_end,
                        )
                    )
                )
                lotteries = result.scalars().all()
                for lottery in lotteries:
                    try:
                        message = (
                            "Мы так и не получили ваши контакты и не можем связаться с вами для выдачи сертификата на 5 000 руб.\n\n"
                            "📞 Пожалуйста, пришлите номер вашего телефона, чтобы наш менеджер связался с вами для выдачи приза."
                        )
                        await self.bot.send_message(lottery.winner_user_id, message)
                        logger.info(
                            f"Напоминание отправлено пользователю {lottery.winner_user_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при отправке напоминания пользователю {lottery.winner_user_id}: {str(e)}"
                        )
        except Exception as e:
            logger.error(
                f"Критическая ошибка в задаче напоминания о контакте: {str(e)}"
            )

    def start_scheduler(self):
        """Запускает планировщик задач"""
        if self.is_running:
            logger.warning("Планировщик уже запущен")
            return

        try:
            # Добавляем задачу еженедельного розыгрыша (каждый понедельник в 10:00)
            self.scheduler.add_job(
                self.conduct_weekly_lottery_job,
                trigger=CronTrigger(
                    day_of_week=0, hour=10, minute=0
                ),  # 0 = понедельник
                id="weekly_lottery",
                name="Еженедельный розыгрыш сертификатов OZON",
                replace_existing=True,
                max_instances=1,
            )

            # Добавляем задачу напоминания о предоставлении контактных данных победителям (каждый вторник в 10:00)
            self.scheduler.add_job(
                self.send_contact_reminders_job,
                trigger=CronTrigger(day_of_week=1, hour=11, minute=0),  # 1 = вторник
                id="contact_reminder",
                name="Напоминание победителям о предоставлении контактных данных",
                replace_existing=True,
                max_instances=1,
            )

            # Экспорт пользователей каждые 15 минут
            self.scheduler.add_job(
                self.export_users_to_sheets_job,
                trigger=CronTrigger(minute="*/15"),
                id="export_users_to_sheets",
                name="Экспорт пользователей в Google Sheets (каждые 15 минут)",
                replace_existing=True,
                max_instances=1,
            )

            self.scheduler.start()
            self.is_running = True
            logger.info(
                "Планировщик еженедельных розыгрышей запущен (каждый понедельник в 10:00)"
            )

        except Exception as e:
            logger.error(f"Ошибка при запуске планировщика: {str(e)}")

    def stop_scheduler(self):
        """Останавливает планировщик задач"""
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Планировщик еженедельных розыгрышей остановлен")

        except Exception as e:
            logger.error(f"Ошибка при остановке планировщика: {str(e)}")

    async def run_lottery_manually(self) -> dict:
        """Ручной запуск еженедельного розыгрыша"""
        try:
            logger.info("Ручной запуск еженедельного розыгрыша")

            async with async_session() as session:
                result = await weekly_lottery_service.conduct_lottery(session, self.bot)
                return result

        except Exception as e:
            logger.error(f"Ошибка при ручном запуске розыгрыша: {str(e)}")
            return {"success": False, "error": f"Ошибка при ручном запуске: {str(e)}"}

    def get_next_lottery_time(self) -> Optional[datetime]:
        """Возвращает время следующего розыгрыша"""
        if not self.is_running:
            return None

        try:
            job = self.scheduler.get_job("weekly_lottery")
            if job and job.next_run_time:
                return job.next_run_time
            return None

        except Exception as e:
            logger.error(f"Ошибка при получении времени следующего розыгрыша: {str(e)}")
            return None


# Глобальный экземпляр планировщика
lottery_scheduler = LotteryScheduler()
