import asyncio
from sqlalchemy import text
from database import engine


async def main():
    """
    Объединенная миграция базы данных
    Включает все изменения из отдельных файлов миграций:
    - migration_add_utm.py
    - migration_create_admin_users.py
    - migration_add_receipt_address.py
    - migration_add_receipt_columns.py
    - migration_add_promocode_id.py
    """
    async with engine.begin() as conn:
        print("Начинаем выполнение объединенной миграции...")

        # 1. Добавляем колонку utm в таблицу users
        print("1. Добавляем колонку utm в таблицу users...")
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS utm VARCHAR(200)")
        )
        print("✓ Колонка 'utm' добавлена в таблицу 'users'")

        # 2. Создаем таблицу admin_users
        print("2. Создаем таблицу admin_users...")
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
        print("✓ Таблица 'admin_users' создана")

        # 3. Добавляем колонку address в таблицу receipts
        print("3. Добавляем колонку address в таблицу receipts...")
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS address TEXT")
        )
        print("✓ Колонка 'address' добавлена в таблицу 'receipts'")

        # 4. Добавляем колонки aisida_items и raw_api_response в таблицу receipts
        print(
            "4. Добавляем колонки aisida_items и raw_api_response в таблицу receipts..."
        )
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS aisida_items TEXT")
        )
        await conn.execute(
            text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS raw_api_response TEXT")
        )
        print(
            "✓ Колонки 'aisida_items' и 'raw_api_response' добавлены в таблицу 'receipts'"
        )

        # 5. Добавляем колонку promocode_id в таблицу prizes и внешний ключ
        print("5. Добавляем колонку promocode_id в таблицу prizes...")
        await conn.execute(
            text("ALTER TABLE prizes ADD COLUMN IF NOT EXISTS promocode_id INTEGER")
        )

        # Добавляем внешний ключ на таблицу promocodes
        print("6. Добавляем внешний ключ для promocode_id...")
        try:
            await conn.execute(
                text(
                    "ALTER TABLE prizes ADD CONSTRAINT fk_prizes_promocode_id FOREIGN KEY (promocode_id) REFERENCES promocodes(id)"
                )
            )
            print("✓ Внешний ключ успешно добавлен")
        except Exception as e:
            print(
                f"⚠ Предупреждение: Не удалось добавить внешний ключ (возможно, уже существует): {e}"
            )

        print("✓ Колонка 'promocode_id' добавлена в таблицу 'prizes'")

        print("\n🎉 Объединенная миграция успешно выполнена!")
        print("Все изменения из отдельных файлов миграций применены.")


if __name__ == "__main__":
    asyncio.run(main())
