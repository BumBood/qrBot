from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class WeeklyLottery(Base):
    """Модель еженедельного розыгрыша сертификатов OZON на 5000 руб"""

    __tablename__ = "weekly_lotteries"

    id = Column(Integer, primary_key=True)  # ID розыгрыша
    week_start = Column(DateTime, nullable=False)  # Начало недели (понедельник 00:00)
    week_end = Column(DateTime, nullable=False)  # Конец недели (воскресенье 23:59)
    winner_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)  # ID победителя
    winner_receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=True)  # ID выигрышного чека
    prize_amount = Column(Integer, default=5000)  # Размер приза в рублях
    contact_info = Column(String(100), default="")  # Контакт для связи
    contact_sent = Column(Boolean, default=False)  # Статус: пользователь отправил контакт или нет
    conducted_at = Column(DateTime, nullable=True)  # Дата проведения розыгрыша
    notification_sent = Column(Boolean, default=False)  # Отправлено ли уведомление
    created_at = Column(DateTime, server_default=func.now())  # Дата создания записи

    # Отношения
    winner_user = relationship("User", foreign_keys=[winner_user_id])
    winner_receipt = relationship("Receipt", foreign_keys=[winner_receipt_id])

    def __repr__(self):
        return f"<WeeklyLottery(id={self.id}, week_start={self.week_start}, winner_user_id={self.winner_user_id})>"
