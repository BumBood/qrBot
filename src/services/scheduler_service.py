import asyncio
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.weekly_lottery_service import weekly_lottery_service
from database import async_session
from logger import logger


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
