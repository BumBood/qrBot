from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DB_URL

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем асинхронный движок SQLAlchemy
engine = create_async_engine(DB_URL, echo=True)

# Создаем фабрику сессий
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Функция для получения сессии базы данных
async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
