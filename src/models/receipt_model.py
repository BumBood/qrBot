from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Numeric,
    ForeignKey,
    Text,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Receipt(Base):
    """Модель чека в системе"""

    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)  # ID чека
    user_id = Column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )  # Ссылка на пользователя

    fn = Column(String(17), nullable=False)  # ФН
    fd = Column(String(6), nullable=False)  # ФД
    fpd = Column(String(10), nullable=False)  # ФПД
    amount = Column(Numeric(10, 2), nullable=False)  # Сумма
    status = Column(String(20), default="pending")  # Статус (pending/verified/rejected)
    verification_date = Column(DateTime, nullable=True)  # Дата проверки
    items_count = Column(Integer, default=0)  # Количество товаров "Айсида"
    pharmacy = Column(String(100), nullable=True)  # Аптека
    address = Column(Text, nullable=True)  # Адрес магазина
    aisida_items = Column(
        Text, nullable=True
    )  # JSON списка наименований товаров Айсида
    raw_api_response = Column(Text, nullable=True)  # Полный ответ API в формате JSON
    created_at = Column(DateTime, server_default=func.now())  # Дата создания

    # Отношение к пользователю
    user = relationship("User", backref="receipts")

    def __repr__(self):
        return f"<Receipt(id={self.id}, user_id={self.user_id}, status={self.status})>"
