import asyncio
from sqlalchemy import text
from database import engine


async def main():
    async with engine.begin() as conn:
        # Добавляем колонку promocode_id в таблицу prizes
        await conn.execute(
            text("ALTER TABLE prizes ADD COLUMN IF NOT EXISTS promocode_id INTEGER")
        )

        # Добавляем внешний ключ на таблицу promocodes
        try:
            await conn.execute(
                text(
                    "ALTER TABLE prizes ADD CONSTRAINT fk_prizes_promocode_id FOREIGN KEY (promocode_id) REFERENCES promocodes(id)"
                )
            )
            print("Foreign key constraint added successfully")
        except Exception as e:
            print(
                f"Warning: Could not add foreign key constraint (it may already exist): {e}"
            )

        print("Column 'promocode_id' added to 'prizes' table")


if __name__ == "__main__":
    asyncio.run(main())
