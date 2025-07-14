from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.weekly_lottery_model import WeeklyLottery

from services.weekly_lottery_service import weekly_lottery_service
from services.scheduler_service import lottery_scheduler
from handlers.base_handler import get_main_menu_keyboard
from logger import logger

from aiogram.types import CallbackQuery

# Создаем роутер для еженедельного розыгрыша
router = Router()


@router.callback_query(F.data == "weekly_lottery")
async def callback_weekly_lottery(callback: CallbackQuery, session: AsyncSession):
    """
    Обрабатывает нажатие на кнопку "Еженедельный розыгрыш OZON"
    """
    try:
        # Получаем историю последних розыгрышей
        lottery_history = await weekly_lottery_service.get_lottery_history(
            session, limit=5
        )

        # Получаем время следующего розыгрыша
        next_lottery_time = lottery_scheduler.get_next_lottery_time()

        # Формируем текст сообщения
        text = (
            "<b>🎁 Еженедельный розыгрыш сертификатов OZON на 5000 руб.</b>\n\n"
            "Каждую неделю мы разыгрываем сертификат OZON на 5000 руб. среди всех участников, "
            "зарегистрировавших чеки с понедельника по воскресенье.\n\n"
            "<b>Условия участия:</b>\n"
            "• Зарегистрируйте чек с товарами «Айсида»\n"
            "• Чек должен быть подтверждён\n"
            "• Розыгрыш проводится каждый понедельник\n\n"
        )

        # Добавляем информацию о следующем розыгрыше
        if next_lottery_time:
            text += f"📅 <b>Следующий розыгрыш:</b> {next_lottery_time.strftime('%d.%m.%Y в %H:%M')}\n\n"

        # Добавляем историю розыгрышей
        if lottery_history:
            text += "<b>🏆 Последние розыгрыши:</b>\n"
            for i, lottery in enumerate(lottery_history, 1):
                if lottery.winner_user_id:
                    winner_text = f"Пользователь #{lottery.winner_user_id}"
                    text += (
                        f"{i}. {lottery.week_start.strftime('%d.%m')} - {lottery.week_end.strftime('%d.%m.%Y')}: "
                        f"{winner_text} (чек №{lottery.winner_receipt_id})\n"
                    )
                else:
                    text += (
                        f"{i}. {lottery.week_start.strftime('%d.%m')} - {lottery.week_end.strftime('%d.%m.%Y')}: "
                        f"Участников не было\n"
                    )
        else:
            text += "Розыгрыши ещё не проводились.\n"

        text += "\nУдачи в следующем розыгрыше! 🍀"

        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Зарегистрировать чек", callback_data="register_receipt")
        builder.button(text="📝 Мои чеки", callback_data="my_receipts")
        builder.button(text="Назад в меню", callback_data="main_menu")
        builder.adjust(1)

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при обработке запроса еженедельного розыгрыша: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при загрузке информации о розыгрыше. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()


@router.callback_query(F.data == "lottery_history")
async def callback_lottery_history(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает подробную историю еженедельных розыгрышей
    """
    try:
        lottery_history = await weekly_lottery_service.get_lottery_history(
            session, limit=10
        )

        if not lottery_history:
            text = "История розыгрышей пуста."
        else:
            text = "<b>📜 История еженедельных розыгрышей:</b>\n\n"

            for i, lottery in enumerate(lottery_history, 1):
                conducted_date = (
                    lottery.conducted_at.strftime("%d.%m.%Y в %H:%M")
                    if lottery.conducted_at
                    else "Не проведён"
                )

                text += f"<b>{i}. Неделя {lottery.week_start.strftime('%d.%m')} - {lottery.week_end.strftime('%d.%m.%Y')}</b>\n"
                text += f"Проведён: {conducted_date}\n"

                if lottery.winner_user_id:
                    text += f"🏆 Победитель: Пользователь #{lottery.winner_user_id}\n"
                    text += f"🧾 Выигрышный чек: №{lottery.winner_receipt_id}\n"
                    text += f"💰 Приз: {lottery.prize_amount} руб.\n"

                    notification_status = (
                        "✅ Да" if lottery.notification_sent else "❌ Нет"
                    )
                    text += f"📱 Уведомление отправлено: {notification_status}\n"
                else:
                    text += "👥 Участников не было\n"

                text += "\n"

        builder = InlineKeyboardBuilder()
        builder.button(text="🎁 К розыгрышу", callback_data="weekly_lottery")
        builder.button(text="Назад в меню", callback_data="main_menu")
        builder.adjust(1)

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при показе истории розыгрышей: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при загрузке истории. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()
class ContactLotteryState(StatesGroup):
    waiting_for_contact = State()

@router.callback_query(lambda c: c.data and c.data.startswith("send_contact"))
async def callback_send_contact(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает нажатие кнопки отправки контакта"""
    await callback.answer()
    # Убираем кнопку, чтобы не нажимали повторно
    try:
        await callback.message.edit_reply_markup(None)
    except Exception:
        pass
    # Просим пользователя прислать контакт текстом
    await callback.message.answer(
        "📲 Пожалуйста, введите номер вашего телефона удобным для вас способом (текстом)."
    )
    # Устанавливаем состояние ожидания контакта
    await state.set_state(ContactLotteryState.waiting_for_contact)





@router.message(ContactLotteryState.waiting_for_contact)
async def handle_winner_contact(
    message: Message, session: AsyncSession, state: FSMContext
):
    """
    Обрабатывает получение контактных данных от победителя еженедельного розыгрыша
    """
    # Ищем последнюю лотерею для этого пользователя без контакта
    result = await session.execute(
        select(WeeklyLottery)
        .where(
            and_(
                WeeklyLottery.winner_user_id == message.from_user.id,
                WeeklyLottery.contact_sent == False,
            )
        )
        .order_by(WeeklyLottery.conducted_at.desc())
        .limit(1)
    )
    lottery = result.scalars().first()
    if lottery:
        lottery.contact_info = message.text
        lottery.contact_sent = True
        await session.commit()
        await message.answer(
            "Спасибо! Ваш контакт получен. Ожидайте, менеджер свяжется с вами."
        )
        # Завершаем состояние
        await state.clear()


def register_weekly_lottery_handlers() -> Router:
    """
    Регистрирует обработчики для еженедельного розыгрыша
    """
    return router
