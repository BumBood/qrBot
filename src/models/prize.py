from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Prize(Base):
    """Модель подарка в системе"""

    __tablename__ = "prizes"

    id = Column(Integer, primary_key=True)  # ID подарка
    receipt_id = Column(
        Integer, ForeignKey("receipts.id"), nullable=False
    )  # Ссылка на чек
    type = Column(String(20), nullable=False)  # Тип (coupon/phone)
    code = Column(String(50), nullable=True)  # Промокод
    phone_last4 = Column(String(4), nullable=True)  # Последние 4 цифры телефона
    issued_at = Column(DateTime, server_default=func.now())  # Дата выдачи

    # Отношение к чеку
    receipt = relationship("Receipt", backref="prizes")

    def __repr__(self):
        return f"<Prize(id={self.id}, type={self.type}, receipt_id={self.receipt_id})>"
