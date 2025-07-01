import asyncio
import os
import sys

# Добавляем папку src в PYTHONPATH
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from database import engine
from sqlalchemy import text


async def upgrade():
    """
    Добавляет колонку contact_sent в таблицу weekly_lotteries
    """
    async with engine.begin() as conn:
        # Добавляем колонку для статуса отправки контакта пользователем
        await conn.execute(
            text(
                """
ALTER TABLE weekly_lotteries
ADD COLUMN IF NOT EXISTS contact_sent BOOLEAN DEFAULT FALSE;
                """
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
    print("Миграция выполнена успешно.")
