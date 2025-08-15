import random
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.receipt_model import Receipt
from models.user_model import User
from logger import logger


async def select_winner(session: AsyncSession) -> int:
    """
    Выбирает случайный подтвержденный чек для розыгрыша

    Args:
        session: Сессия базы данных

    Returns:
        int: ID пользователя-победителя или None, если нет подходящих чеков
    """
    try:
        # Получаем все подтвержденные чеки с хотя бы 1 позицией Айсида
        verified_receipts = await session.execute(
            select(Receipt).where(
                and_(
                    Receipt.status == "verified",
                    Receipt.items_count > 0,
                )
            )
        )

        receipts_list = verified_receipts.scalars().all()

        if not receipts_list:
            logger.warning("Нет подтвержденных чеков для розыгрыша")
            return None

        # Выбираем случайный чек
        winner_receipt = random.choice(receipts_list)

        logger.info(
            f"Выбран победитель розыгрыша: чек {winner_receipt.id}, пользователь {winner_receipt.user_id}"
        )

        return winner_receipt.user_id

    except Exception as e:
        logger.error(f"Ошибка при выборе победителя розыгрыша: {str(e)}")
        return None


async def notify_winner(session: AsyncSession, bot, user_id: int) -> bool:
    """
    Отправляет сообщение победителю розыгрыша

    Args:
        session: Сессия базы данных
        bot: Экземпляр бота для отправки сообщений
        user_id: ID пользователя-победителя

    Returns:
        bool: True, если уведомление отправлено успешно, иначе False
    """
    try:
        # Получаем информацию о пользователе
        user_query = await session.execute(select(User).where(User.id == user_id))
        user = user_query.scalars().first()

        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден")
            return False

        # Отправляем сообщение победителю
        await bot.send_message(
            user_id,
            "🎉 Поздравляем! Вы стали победителем розыгрыша главного приза! "
            "В ближайшее время с вами свяжется наш менеджер для уточнения деталей получения приза.",
        )

        logger.info(f"Отправлено уведомление о победе пользователю {user_id}")

        return True

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления победителю: {str(e)}")
        return False


async def notify_participants(session: AsyncSession, bot, winner_id: int) -> dict:
    """
    Рассылает уведомления всем участникам о результатах розыгрыша

    Args:
        session: Сессия базы данных
        bot: Экземпляр бота для отправки сообщений
        winner_id: ID пользователя-победителя

    Returns:
        dict: Статистика рассылки
    """
    try:
        # Получаем всех пользователей, кроме победителя
        users_query = await session.execute(select(User).where(User.id != winner_id))
        users = users_query.scalars().all()

        sent_count = 0
        error_count = 0

        # Отправляем сообщения всем участникам
        for user in users:
            try:
                await bot.send_message(
                    user.id,
                    "Розыгрыш главного приза завершен! К сожалению, в этот раз вы не стали победителем. "
                    "Но не расстраивайтесь, впереди еще много розыгрышей! "
                    "Продолжайте регистрировать чеки и участвовать в акции.",
                )
                sent_count += 1
            except Exception as e:
                logger.error(
                    f"Ошибка при отправке уведомления пользователю {user.id}: {str(e)}"
                )
                error_count += 1

        logger.info(
            f"Отправлено {sent_count} уведомлений участникам розыгрыша, ошибок: {error_count}"
        )

        return {"success": True, "sent_count": sent_count, "error_count": error_count}

    except Exception as e:
        logger.error(f"Ошибка при рассылке уведомлений участникам: {str(e)}")
        return {"success": False, "error": str(e)}
