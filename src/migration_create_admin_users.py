import asyncio
from sqlalchemy import text
from database import engine


async def main():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(128) NOT NULL,
                created_at TIMESTAMP DEFAULT now()
            )
            """
            )
        )
        print("Table 'admin_users' created")


if __name__ == "__main__":
    asyncio.run(main())
