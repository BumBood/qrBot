from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base


class PromoSetting(Base):
    """Модель настроек промокода акции"""

    __tablename__ = "promo_settings"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True)  # Текст промокода
    discount_single = Column(
        Integer, nullable=False
    )  # Скидка при покупке 1 средства (руб)
    discount_multi = Column(
        Integer, nullable=False
    )  # Скидка при покупке 2+ средств (руб)
    created_at = Column(DateTime, server_default=func.now())  # Дата создания записи
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )  # Дата обновления записи
