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
from config import ADMIN_IDS

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

        # Добавляем кнопку управления розыгрышами для администраторов
        if str(callback.from_user.id) in ADMIN_IDS:
            builder.button(
                text="⚙️ Управление розыгрышами",
                callback_data="admin_lottery_management",
            )

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


<<<<<<< HEAD
=======
class ManualSelectState(StatesGroup):
    waiting_for_receipt_id = State()


>>>>>>> ccc01473e1b548e584dbb1e6792623970819e2a9
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


@router.callback_query(F.data == "admin_lottery_management")
async def callback_admin_lottery_management(
    callback: CallbackQuery, session: AsyncSession
):
    """
    Обработчик управления розыгрышами для администраторов
    """
    # Проверяем, что пользователь администратор
    if str(callback.from_user.id) not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия")
        return

    try:
        # Получаем последние розыгрыши
        recent_lotteries = await weekly_lottery_service.get_lottery_history(
            session, limit=5
        )

        text = "<b>⚙️ Управление розыгрышами</b>\n\n"

        if recent_lotteries:
            text += "<b>Последние розыгрыши:</b>\n"
            for i, lottery in enumerate(recent_lotteries, 1):
                status_icon = "✅" if lottery.notification_sent else "⏳"
                winner_info = (
                    f"#{lottery.winner_user_id} (чек #{lottery.winner_receipt_id})"
                    if lottery.winner_user_id
                    else "Нет победителя"
                )
                text += f"{i}. {lottery.week_start.strftime('%d.%m')} - {lottery.week_end.strftime('%d.%m.%Y')} {status_icon}\n"
                text += f"   Победитель: {winner_info}\n\n"
        else:
            text += "Розыгрыши ещё не проводились.\n\n"

        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.button(text="🎯 Провести розыгрыш", callback_data="run_lottery")
        builder.button(
            text="📋 Выбрать победителя вручную", callback_data="manual_select_start"
        )
        builder.button(text="📊 История розыгрышей", callback_data="lottery_history")
        builder.button(text="🔙 Назад", callback_data="weekly_lottery")
        builder.adjust(1)

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при показе управления розыгрышами: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при загрузке управления розыгрышами.",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()


@router.callback_query(F.data == "run_lottery")
async def callback_run_lottery(callback: CallbackQuery, session: AsyncSession):
    """
    Обработчик проведения розыгрыша
    """
    # Проверяем, что пользователь администратор
    if str(callback.from_user.id) not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия")
        return

    try:
        await callback.answer("Проводим розыгрыш...")

        # Проводим розыгрыш за предыдущую неделю
        result = await weekly_lottery_service.conduct_lottery(session)

        if result["success"]:
            if result.get("winner"):
                w = result["winner"]
                message = f"✅ Розыгрыш проведён!\n🏆 Победитель: пользователь #{w['user_id']}\n🧾 Чек: #{w['receipt_id']}"
            else:
                message = "✅ Розыгрыш проведён. Участников не было."
        else:
            message = f"❌ Ошибка: {result.get('error')}"

        await callback.message.edit_text(message, reply_markup=get_main_menu_keyboard())

    except Exception as e:
        logger.error(f"Ошибка при проведении розыгрыша: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при проведении розыгрыша.",
            reply_markup=get_main_menu_keyboard(),
        )


@router.callback_query(F.data == "manual_select_start")
async def callback_manual_select_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """
    Начало процесса ручного выбора победителя
    """
    # Проверяем, что пользователь администратор
    if str(callback.from_user.id) not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия")
        return

    try:
        # Получаем последний проведённый розыгрыш
        recent_lotteries = await weekly_lottery_service.get_lottery_history(
            session, limit=1
        )

        if not recent_lotteries:
            await callback.message.edit_text(
                "❌ Нет проведённых розыгрышей для выбора победителя.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        lottery = recent_lotteries[0]

        # Проверяем, что розыгрыш ещё не подтверждён
        if lottery.notification_sent:
            await callback.message.edit_text(
                "❌ Этот розыгрыш уже подтверждён и победителя нельзя изменить.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        # Получаем подходящие чеки
        eligible_receipts = await weekly_lottery_service.get_eligible_receipts(
            session, lottery.week_start, lottery.week_end
        )

        if not eligible_receipts:
            await callback.message.edit_text(
                "❌ Нет подходящих чеков для выбора победителя.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        # Сохраняем информацию о розыгрыше в состоянии
        await state.update_data(lottery_id=lottery.id)

        # Показываем список чеков
        text = f"<b>🎯 Выбор победителя вручную</b>\n\n"
        text += f"Неделя: {lottery.week_start.strftime('%d.%m')} - {lottery.week_end.strftime('%d.%m.%Y')}\n"
        text += f"Количество участников: {len(eligible_receipts)}\n\n"
        text += "<b>Подходящие чеки:</b>\n"

        for i, receipt in enumerate(
            eligible_receipts[:10], 1
        ):  # Показываем первые 10 чеков
            user_info = (
                f"@{receipt.user.username}"
                if receipt.user.username
                else receipt.user.full_name
            )
            text += f"{i}. Чек #{receipt.id} - {user_info} ({receipt.amount} руб.)\n"

        if len(eligible_receipts) > 10:
            text += f"... и ещё {len(eligible_receipts) - 10} чеков\n"

        text += "\n<b>Введите номер чека для выбора победителем:</b>"

        # Создаем клавиатуру с кнопками номеров чеков
        builder = InlineKeyboardBuilder()

        # Показываем кнопки для первых 10 чеков
        for i, receipt in enumerate(eligible_receipts[:10], 1):
            builder.button(
                text=f"Чек #{receipt.id}", callback_data=f"select_receipt:{receipt.id}"
            )

        builder.button(text="🔙 Назад", callback_data="admin_lottery_management")
        builder.adjust(2)

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )

        # Устанавливаем состояние ожидания ввода номера чека
        await state.set_state(ManualSelectState.waiting_for_receipt_id)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при начале ручного выбора: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при начале выбора победителя.",
            reply_markup=get_main_menu_keyboard(),
        )
        await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("select_receipt:"))
async def callback_select_receipt(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    """
    Обработчик выбора чека из списка
    """
    # Проверяем, что пользователь администратор
    if str(callback.from_user.id) not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия")
        return

    try:
        # Получаем ID чека из callback_data
        receipt_id = int(callback.data.split(":")[1])

        # Получаем ID розыгрыша из состояния
        data = await state.get_data()
        lottery_id = data.get("lottery_id")

        if not lottery_id:
            await callback.message.edit_text(
                "❌ Ошибка: не найден ID розыгрыша.",
                reply_markup=get_main_menu_keyboard(),
            )
            await state.clear()
            return

        # Выполняем выбор победителя
        result = await weekly_lottery_service.manual_select_winner(
            session, lottery_id, receipt_id
        )

        if result["success"]:
            message = f"✅ {result['message']}"
        else:
            message = f"❌ Ошибка: {result['error']}"

        await callback.message.edit_text(message, reply_markup=get_main_menu_keyboard())

        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при выборе чека: {str(e)}")
        await callback.message.edit_text(
            "Произошла ошибка при выборе чека.", reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
        await callback.answer()


@router.message(ManualSelectState.waiting_for_receipt_id)
async def handle_manual_receipt_selection(
    message: Message, session: AsyncSession, state: FSMContext
):
    """
    Обрабатывает ввод номера чека для ручного выбора победителя
    """
    # Проверяем, что пользователь администратор
    if str(message.from_user.id) not in ADMIN_IDS:
        return

    try:
        # Получаем введённый текст
        receipt_id_text = message.text.strip()

        # Проверяем, что введено число
        if not receipt_id_text.isdigit():
            await message.answer(
                "❌ Пожалуйста, введите корректный номер чека (только цифры)."
            )
            return

        receipt_id = int(receipt_id_text)

        # Получаем ID розыгрыша из состояния
        data = await state.get_data()
        lottery_id = data.get("lottery_id")

        if not lottery_id:
            await message.answer("❌ Ошибка: не найден ID розыгрыша.")
            await state.clear()
            return

        # Выполняем выбор победителя
        result = await weekly_lottery_service.manual_select_winner(
            session, lottery_id, receipt_id
        )

        if result["success"]:
            await message.answer(f"✅ {result['message']}")
        else:
            await message.answer(f"❌ Ошибка: {result['error']}")

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при обработке ввода чека: {str(e)}")
        await message.answer("Произошла ошибка при выборе чека.")
        await state.clear()


def register_weekly_lottery_handlers() -> Router:
    """
    Регистрирует обработчики для еженедельного розыгрыша
    """
    return router
