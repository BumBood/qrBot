from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
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
    type = Column(String(20), nullable=False)  # Тип (promocode_200/promocode_500)
    code = Column(String(50), nullable=True)  # Промокод (legacy)
    promocode_id = Column(
        Integer, ForeignKey("promocodes.id"), nullable=True
    )  # Ссылка на промокод в БД
    discount_amount = Column(Integer, nullable=True)  # Размер скидки в рублях
    used = Column(Boolean, default=False)  # Использован ли промокод
    phone_last4 = Column(
        String(4), nullable=True
    )  # Последние 4 цифры телефона (legacy)
    issued_at = Column(DateTime, server_default=func.now())  # Дата выдачи

    # Отношения
    receipt = relationship("Receipt", backref="prizes")
    promocode = relationship("Promocode", backref="prizes")

    def __repr__(self):
        return f"<Prize(id={self.id}, type={self.type}, receipt_id={self.receipt_id})>"
