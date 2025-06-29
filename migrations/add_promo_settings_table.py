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
    Выполняет создание таблицы promo_settings и добавление настроек по умолчанию
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
CREATE TABLE IF NOT EXISTS promo_settings (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    discount_single INTEGER NOT NULL,
    discount_multi INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Добавляем запись с промокодом по умолчанию
INSERT INTO promo_settings (code, discount_single, discount_multi)
SELECT 'ЛЕТО_КРАСОТЫ', 200, 500
WHERE NOT EXISTS (SELECT 1 FROM promo_settings);
"""
            )
        )


if __name__ == "__main__":
    asyncio.run(upgrade())
    print("Миграция выполнена успешно.")
