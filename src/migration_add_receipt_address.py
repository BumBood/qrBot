import asyncio
from sqlalchemy import text
from database import engine


async def main():
    async with engine.begin() as conn:
        # Добавляем колонку address в таблицу receipts
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS address TEXT")
        )
        print("Column 'address' added to 'receipts' table")


if __name__ == "__main__":
    asyncio.run(main())
