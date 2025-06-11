from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base


class Promocode(Base):
    """Модель промокода в системе"""

    __tablename__ = "promocodes"

    id = Column(Integer, primary_key=True)  # ID промокода
    code = Column(String(50), nullable=False, unique=True)  # Промокод
    discount_amount = Column(
        Integer, nullable=False
    )  # Размер скидки в рублях (200 или 500)
    is_used = Column(Boolean, default=False)  # Использован ли промокод
    is_active = Column(
        Boolean, default=True
    )  # Активен ли промокод (для деактивации админом)
    created_at = Column(DateTime, server_default=func.now())  # Дата создания
    used_at = Column(DateTime, nullable=True)  # Дата использования

    def __repr__(self):
        return f"<Promocode(id={self.id}, code={self.code}, discount_amount={self.discount_amount}, is_used={self.is_used})>"
