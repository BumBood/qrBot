from sqlalchemy import Column, BigInteger, String, DateTime
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """Модель пользователя в системе"""

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)  # Telegram ID пользователя
    username = Column(String(32), nullable=True)  # username в Telegram
    full_name = Column(String(100), nullable=False)  # Имя пользователя
    registered_at = Column(DateTime, server_default=func.now())  # Дата регистрации
    phone_last4 = Column(String(4), nullable=True)  # Последние 4 цифры телефона

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
