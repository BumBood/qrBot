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
    Изменяет тип столбца winner_user_id в таблице weekly_lotteries с INTEGER на BIGINT
    """
    async with engine.begin() as conn:
        # Изменяем тип столбца winner_user_id на BIGINT
        await conn.execute(
            text(
                """
ALTER TABLE weekly_lotteries
ALTER COLUMN winner_user_id TYPE BIGINT;
                """
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
    print("Миграция выполнена успешно.")
