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
    Выполняет добавление новых колонок utm_source, utm_medium и utm_campaign в таблицу users
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
ALTER TABLE users
    ADD COLUMN utm_source VARCHAR(200),
    ADD COLUMN utm_medium VARCHAR(200),
    ADD COLUMN utm_campaign VARCHAR(200);
"""
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
    print("Миграция выполнена успешно.")
