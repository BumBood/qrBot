import asyncio
from sqlalchemy import text
from database import engine


async def main():
    async with engine.begin() as conn:
        # Добавляем колонки в таблицу receipts
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS aisida_items TEXT")
        )
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS raw_api_response TEXT")
        )
        print("Columns 'aisida_items' and 'raw_api_response' added to 'receipts'")


if __name__ == "__main__":
    asyncio.run(main())
