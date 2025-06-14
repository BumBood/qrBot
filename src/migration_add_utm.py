import asyncio
from sqlalchemy import text
from database import engine


async def main():
    async with engine.begin() as conn:
        # Добавляем колонку utm в таблицу users
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS utm VARCHAR(200)")
        )
        print("Column 'utm' added to 'users' table")


if __name__ == "__main__":
    asyncio.run(main())
