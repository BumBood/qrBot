from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import random

from config import ADMIN_PANEL_ENABLED
from services.prize_service import issue_prize, promo_manager
from services.promocode_service import promocode_service
from services.weekly_lottery_service import WeeklyLotteryService
from services.lottery_service import select_winner, notify_winner, notify_participants
from models.receipt_model import Receipt
from models.user_model import User
from models.prize_model import Prize
from logger import logger

# Создаем роутер для админки
router = Router()


# Состояния для FSM управления промокодами
class AdminPromoStates(StatesGroup):
    waiting_for_promocodes_200 = State()  # Ожидание промокодов на 200р
    waiting_for_promocodes_500 = State()  # Ожидание промокодов на 500р


def get_admin_keyboard():
    """Создает клавиатуру админки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Выдать промокод", callback_data="admin_issue_promo")
    builder.button(
        text="🎫 Управление промокодами", callback_data="admin_manage_promos"
    )
    builder.button(
        text="🎲 Провести еженедельную лотерею", callback_data="admin_weekly_lottery"
    )
    builder.button(
        text="🏆 Провести главную лотерею", callback_data="admin_main_lottery"
    )
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📋 Последние чеки", callback_data="admin_recent_receipts")
    builder.button(text="🔄 Обновить", callback_data="admin_menu")
    builder.adjust(2)
    return builder.as_markup()


def get_promo_management_keyboard():
    """Создает клавиатуру управления промокодами"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить промокоды 200р", callback_data="admin_add_promo_200"
    )
    builder.button(
        text="➕ Добавить промокоды 500р", callback_data="admin_add_promo_500"
    )
    builder.button(text="📊 Статистика промокодов", callback_data="admin_promo_stats")
    builder.button(text="📋 Список промокодов", callback_data="admin_promo_list")
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")
    builder.adjust(2)
    return builder.as_markup()


@router.message(F.text.in_(["/admin", "админ", "Админ", "АДМИН"]))
async def admin_command(message: Message, session: AsyncSession):
    """
    Обрабатывает команду /admin для входа в админку
    """
    if not ADMIN_PANEL_ENABLED:
        await message.answer("Админка отключена.")
        return

    # Получаем статистику
    stats = await get_admin_stats(session)
    promo_stats = await promocode_service.get_promocodes_stats(session)

    text = (
        "🔧 <b>ВРЕМЕННАЯ АДМИНКА ДЛЯ ТЕСТОВ</b>\n\n"
        "📊 <b>Текущая статистика:</b>\n"
        f"👥 Пользователей: {stats['users_count']}\n"
        f"🧾 Чеков: {stats['receipts_count']}\n"
        f"✅ Подтвержденных: {stats['verified_receipts']}\n"
        f"🎁 Промокодов выдано: {stats['prizes_count']}\n\n"
        f"💰 <b>Промокоды в БД:</b>\n"
        f"📦 Всего в системе: {promo_stats['total_count']}\n"
        f"💎 Доступно 200р: {promo_stats['available_200']}\n"
        f"💎 Доступно 500р: {promo_stats['available_500']}\n"
        f"✅ Использовано 200р: {promo_stats['used_200']}\n"
        f"✅ Использовано 500р: {promo_stats['used_500']}\n\n"
        "<i>Выберите действие:</i>"
    )

    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Обновляет главное меню админки
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    stats = await get_admin_stats(session)
    promo_stats = await promocode_service.get_promocodes_stats(session)

    text = (
        "🔧 <b>ВРЕМЕННАЯ АДМИНКА ДЛЯ ТЕСТОВ</b>\n\n"
        "📊 <b>Текущая статистика:</b>\n"
        f"👥 Пользователей: {stats['users_count']}\n"
        f"🧾 Чеков: {stats['receipts_count']}\n"
        f"✅ Подтвержденных: {stats['verified_receipts']}\n"
        f"🎁 Промокодов выдано: {stats['prizes_count']}\n\n"
        f"💰 <b>Промокоды в БД:</b>\n"
        f"📦 Всего в системе: {promo_stats['total_count']}\n"
        f"💎 Доступно 200р: {promo_stats['available_200']}\n"
        f"💎 Доступно 500р: {promo_stats['available_500']}\n"
        f"✅ Использовано 200р: {promo_stats['used_200']}\n"
        f"✅ Использовано 500р: {promo_stats['used_500']}\n\n"
        "<i>Выберите действие:</i>"
    )

    await callback.message.edit_text(
        text, reply_markup=get_admin_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_issue_promo")
async def admin_issue_promo_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Выдает промокод как будто зарегистрирован чек
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    try:
        # Создаем тестовый чек
        test_receipt = Receipt(
            user_id=callback.from_user.id,
            fn="1234567890123456",
            fd="123456",
            fpd="1234567890",
            amount=1000.0,
            status="verified",
            verification_date=datetime.now(),
            items_count=random.choice([1, 2]),  # Случайно 1 или 2 товара
        )

        session.add(test_receipt)
        await session.flush()  # Получаем ID без коммита

        # Выдаем подарок
        prize_result = await issue_prize(
            session, test_receipt.id, test_receipt.items_count
        )

        if prize_result["success"]:
            await session.commit()
            text = (
                f"✅ <b>Промокод выдан!</b>\n\n"
                f"💰 Сумма скидки: {prize_result['discount_amount']} руб.\n"
                f"🎫 Промокод: <code>{prize_result['code']}</code>\n"
                f"🧾 ID чека: {test_receipt.id}\n"
                f"📦 Товаров Айсида: {test_receipt.items_count}\n\n"
                f"<i>Промокод создан для тестирования.</i>"
            )
        else:
            await session.rollback()
            text = f"❌ Ошибка при выдаче промокода:\n{prize_result.get('error', 'Неизвестная ошибка')}"

    except Exception as e:
        await session.rollback()
        logger.error(f"Ошибка в админке при выдаче промокода: {str(e)}")
        text = f"❌ Произошла ошибка: {str(e)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_weekly_lottery")
async def admin_weekly_lottery_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Проводит еженедельную лотерею принудительно
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    await callback.message.edit_text("⏳ Проводим еженедельную лотерею...")

    try:
        # Проводим лотерею
        bot = callback.bot
        result = await WeeklyLotteryService.conduct_lottery(session, bot)

        if result["success"]:
            if result.get("winner"):
                winner = result["winner"]
                text = (
                    f"🎉 <b>Еженедельная лотерея проведена!</b>\n\n"
                    f"🏆 Победитель: пользователь {winner['user_id']}\n"
                    f"🧾 Выигрышный чек: #{winner['receipt_id']}\n"
                    f"👥 Участников: {result['participants_count']}\n"
                    f"📨 Уведомление отправлено: {'✅' if result['notification_sent'] else '❌'}\n"
                    f"🆔 ID розыгрыша: {winner['lottery_id']}"
                )
            else:
                text = (
                    f"ℹ️ <b>Еженедельная лотерея проведена</b>\n\n"
                    f"👥 Участников: {result['participants_count']}\n"
                    f"📝 {result.get('message', 'Нет участников')}"
                )
        else:
            text = f"❌ Ошибка при проведении лотереи:\n{result.get('error', 'Неизвестная ошибка')}"

    except Exception as e:
        logger.error(f"Ошибка в админке при проведении еженедельной лотереи: {str(e)}")
        text = f"❌ Произошла ошибка: {str(e)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_main_lottery")
async def admin_main_lottery_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Проводит главную лотерею принудительно
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    await callback.message.edit_text("⏳ Проводим главную лотерею...")

    try:
        # Выбираем победителя
        winner_user_id = await select_winner(session)

        if winner_user_id:
            # Уведомляем победителя
            bot = callback.bot
            winner_notified = await notify_winner(session, bot, winner_user_id)

            # Уведомляем остальных участников
            participants_result = await notify_participants(
                session, bot, winner_user_id
            )

            text = (
                f"🎉 <b>Главная лотерея проведена!</b>\n\n"
                f"🏆 Победитель: пользователь {winner_user_id}\n"
                f"📨 Уведомление победителю: {'✅' if winner_notified else '❌'}\n"
                f"📤 Уведомлений участникам: {participants_result.get('sent_count', 0)}\n"
                f"❌ Ошибок при рассылке: {participants_result.get('error_count', 0)}"
            )
        else:
            text = "ℹ️ <b>Главная лотерея проведена</b>\n\nНет подтвержденных чеков для розыгрыша."

    except Exception as e:
        logger.error(f"Ошибка в админке при проведении главной лотереи: {str(e)}")
        text = f"❌ Произошла ошибка: {str(e)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает подробную статистику
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    try:
        stats = await get_detailed_admin_stats(session)

        text = (
            "📊 <b>ПОДРОБНАЯ СТАТИСТИКА</b>\n\n"
            f"👥 <b>Пользователи:</b> {stats['users_count']}\n"
            f"🧾 <b>Всего чеков:</b> {stats['receipts_count']}\n"
            f"⏳ Ожидающих проверки: {stats['pending_receipts']}\n"
            f"✅ Подтвержденных: {stats['verified_receipts']}\n"
            f"❌ Отклоненных: {stats['rejected_receipts']}\n\n"
            f"🎁 <b>Промокоды:</b>\n"
            f"💰 Всего выдано: {stats['prizes_count']}\n"
            f"💎 Промокоды 200р: {stats['promo_200_count']}\n"
            f"💎 Промокоды 500р: {stats['promo_500_count']}\n"
            f"✅ Использованных: {stats['used_prizes']}\n\n"
            f"💵 <b>Суммы чеков:</b>\n"
            f"📈 Общая сумма: {stats['total_amount']:.2f} руб.\n"
            f"📊 Средняя сумма: {stats['avg_amount']:.2f} руб.\n\n"
            f"📦 <b>Товары Айсида:</b>\n"
            f"🔢 Всего товаров: {stats['total_aisida_items']}\n"
            f"📊 Среднее на чек: {stats['avg_aisida_items']:.1f}"
        )

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        text = f"❌ Ошибка при получении статистики: {str(e)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_recent_receipts")
async def admin_recent_receipts_callback(
    callback: CallbackQuery, session: AsyncSession
):
    """
    Показывает последние чеки
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    try:
        # Получаем последние 10 чеков
        from sqlalchemy import select, desc

        recent_receipts = await session.execute(
            select(Receipt).order_by(desc(Receipt.created_at)).limit(10)
        )
        receipts = recent_receipts.scalars().all()

        if not receipts:
            text = "📋 <b>ПОСЛЕДНИЕ ЧЕКИ</b>\n\nЧеков пока нет."
        else:
            text = "📋 <b>ПОСЛЕДНИЕ 10 ЧЕКОВ</b>\n\n"

            for i, receipt in enumerate(receipts, 1):
                status_emoji = {
                    "pending": "⏳",
                    "verified": "✅",
                    "rejected": "❌",
                }.get(receipt.status, "❓")

                text += (
                    f"{i}. {status_emoji} ID: {receipt.id}\n"
                    f"   👤 User: {receipt.user_id}\n"
                    f"   💰 {receipt.amount} руб.\n"
                    f"   📦 Айсида: {receipt.items_count or 0}\n"
                    f"   📅 {receipt.created_at.strftime('%d.%m %H:%M')}\n\n"
                )

    except Exception as e:
        logger.error(f"Ошибка при получении последних чеков: {str(e)}")
        text = f"❌ Ошибка: {str(e)}"

    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в админку", callback_data="admin_menu")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_manage_promos")
async def admin_manage_promos_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает меню управления промокодами
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    promo_stats = await promocode_service.get_promocodes_stats(session)

    text = (
        "🎫 <b>УПРАВЛЕНИЕ ПРОМОКОДАМИ</b>\n\n"
        f"📦 <b>Всего промокодов в БД:</b> {promo_stats['total_count']}\n\n"
        f"💰 <b>Промокоды 200р:</b>\n"
        f"├ Всего: {promo_stats['promo_200_total']}\n"
        f"├ Доступно: {promo_stats['available_200']}\n"
        f"└ Использовано: {promo_stats['used_200']}\n\n"
        f"💎 <b>Промокоды 500р:</b>\n"
        f"├ Всего: {promo_stats['promo_500_total']}\n"
        f"├ Доступно: {promo_stats['available_500']}\n"
        f"└ Использовано: {promo_stats['used_500']}\n\n"
        "<i>Выберите действие:</i>"
    )

    await callback.message.edit_text(
        text, reply_markup=get_promo_management_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_promo_200")
async def admin_add_promo_200_callback(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает ввод промокодов на 200р
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    text = (
        "💰 <b>ДОБАВЛЕНИЕ ПРОМОКОДОВ НА 200 РУБЛЕЙ</b>\n\n"
        "Отправьте промокоды списком, каждый с новой строки.\n"
        "Можно отправить один или несколько промокодов.\n\n"
        "<i>Пример:</i>\n"
        "<code>PROMO200-001\n"
        "PROMO200-002\n"
        "PROMO200-003</code>\n\n"
        "Или отправьте <b>/cancel</b> для отмены."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin_manage_promos")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await state.set_state(AdminPromoStates.waiting_for_promocodes_200)
    await callback.answer()


@router.callback_query(F.data == "admin_add_promo_500")
async def admin_add_promo_500_callback(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает ввод промокодов на 500р
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    text = (
        "💎 <b>ДОБАВЛЕНИЕ ПРОМОКОДОВ НА 500 РУБЛЕЙ</b>\n\n"
        "Отправьте промокоды списком, каждый с новой строки.\n"
        "Можно отправить один или несколько промокодов.\n\n"
        "<i>Пример:</i>\n"
        "<code>PROMO500-001\n"
        "PROMO500-002\n"
        "PROMO500-003</code>\n\n"
        "Или отправьте <b>/cancel</b> для отмены."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin_manage_promos")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await state.set_state(AdminPromoStates.waiting_for_promocodes_500)
    await callback.answer()


@router.message(AdminPromoStates.waiting_for_promocodes_200)
async def process_promocodes_200(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Обрабатывает ввод промокодов на 200р
    """
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "Операция отменена.", reply_markup=get_promo_management_keyboard()
        )
        return

    # Парсим промокоды из сообщения
    codes = [line.strip() for line in message.text.split("\n") if line.strip()]

    if not codes:
        await message.answer("Не найдено ни одного промокода. Попробуйте еще раз.")
        return

    # Добавляем промокоды в БД
    result = await promocode_service.add_promocodes(session, codes, 200)

    if result["success"]:
        text = (
            f"✅ <b>Промокоды на 200р добавлены!</b>\n\n"
            f"📝 Добавлено: {result['added_count']}\n"
            f"⚠️ Пропущено (дубли): {result['skipped_count']}\n"
        )

        if result["errors"] and len(result["errors"]) <= 5:
            text += f"\n<i>Ошибки:</i>\n"
            for error in result["errors"][:5]:
                text += f"• {error}\n"
        elif len(result["errors"]) > 5:
            text += f"\n<i>И еще {len(result['errors']) - 5} ошибок...</i>\n"
    else:
        text = f"❌ <b>Ошибка при добавлении промокодов:</b>\n{result['error']}"

    builder = InlineKeyboardBuilder()
    builder.button(
        text="◀️ Назад к управлению промокодами", callback_data="admin_manage_promos"
    )

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.clear()


@router.message(AdminPromoStates.waiting_for_promocodes_500)
async def process_promocodes_500(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Обрабатывает ввод промокодов на 500р
    """
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "Операция отменена.", reply_markup=get_promo_management_keyboard()
        )
        return

    # Парсим промокоды из сообщения
    codes = [line.strip() for line in message.text.split("\n") if line.strip()]

    if not codes:
        await message.answer("Не найдено ни одного промокода. Попробуйте еще раз.")
        return

    # Добавляем промокоды в БД
    result = await promocode_service.add_promocodes(session, codes, 500)

    if result["success"]:
        text = (
            f"✅ <b>Промокоды на 500р добавлены!</b>\n\n"
            f"📝 Добавлено: {result['added_count']}\n"
            f"⚠️ Пропущено (дубли): {result['skipped_count']}\n"
        )

        if result["errors"] and len(result["errors"]) <= 5:
            text += f"\n<i>Ошибки:</i>\n"
            for error in result["errors"][:5]:
                text += f"• {error}\n"
        elif len(result["errors"]) > 5:
            text += f"\n<i>И еще {len(result['errors']) - 5} ошибок...</i>\n"
    else:
        text = f"❌ <b>Ошибка при добавлении промокодов:</b>\n{result['error']}"

    builder = InlineKeyboardBuilder()
    builder.button(
        text="◀️ Назад к управлению промокодами", callback_data="admin_manage_promos"
    )

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "admin_promo_stats")
async def admin_promo_stats_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает подробную статистику промокодов
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    stats = await promocode_service.get_promocodes_stats(session)

    text = (
        "📊 <b>ПОДРОБНАЯ СТАТИСТИКА ПРОМОКОДОВ</b>\n\n"
        f"📦 <b>Общая статистика:</b>\n"
        f"└ Всего промокодов в БД: {stats['total_count']}\n\n"
        f"💰 <b>Промокоды на 200 рублей:</b>\n"
        f"├ Всего создано: {stats['promo_200_total']}\n"
        f"├ Доступно для выдачи: {stats['available_200']}\n"
        f"└ Уже использовано: {stats['used_200']}\n\n"
        f"💎 <b>Промокоды на 500 рублей:</b>\n"
        f"├ Всего создано: {stats['promo_500_total']}\n"
        f"├ Доступно для выдачи: {stats['available_500']}\n"
        f"└ Уже использовано: {stats['used_500']}\n\n"
    )

    # Добавляем процентную статистику
    if stats["promo_200_total"] > 0:
        usage_200 = (stats["used_200"] / stats["promo_200_total"]) * 100
        text += f"📈 <b>Использование 200р:</b> {usage_200:.1f}%\n"

    if stats["promo_500_total"] > 0:
        usage_500 = (stats["used_500"] / stats["promo_500_total"]) * 100
        text += f"📈 <b>Использование 500р:</b> {usage_500:.1f}%\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="admin_promo_stats")
    builder.button(text="◀️ Назад", callback_data="admin_manage_promos")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_promo_list")
async def admin_promo_list_callback(callback: CallbackQuery, session: AsyncSession):
    """
    Показывает список последних промокодов
    """
    if not ADMIN_PANEL_ENABLED:
        await callback.answer("Админка отключена.")
        return

    # Получаем последние промокоды
    recent_promos = await promocode_service.get_promocodes_list(session, limit=10)

    text = "📋 <b>ПОСЛЕДНИЕ 10 ПРОМОКОДОВ</b>\n\n"

    if not recent_promos:
        text += "❌ Промокодов не найдено."
    else:
        for promo in recent_promos:
            status = "✅ Использован" if promo.is_used else "⭐ Доступен"
            active = "🟢" if promo.is_active else "🔴"
            created = promo.created_at.strftime("%d.%m %H:%M")

            text += (
                f"{active} <code>{promo.code}</code>\n"
                f"├ Скидка: {promo.discount_amount}р\n"
                f"├ Статус: {status}\n"
                f"└ Создан: {created}\n\n"
            )

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="admin_promo_list")
    builder.button(text="◀️ Назад", callback_data="admin_manage_promos")

    await callback.message.edit_text(
        text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


async def get_admin_stats(session: AsyncSession) -> dict:
    """Получает базовую статистику для админки"""
    try:
        from sqlalchemy import select, func

        # Количество пользователей
        users_count = await session.execute(select(func.count(User.id)))
        users_count = users_count.scalar() or 0

        # Количество чеков
        receipts_count = await session.execute(select(func.count(Receipt.id)))
        receipts_count = receipts_count.scalar() or 0

        # Подтвержденные чеки
        verified_receipts = await session.execute(
            select(func.count(Receipt.id)).where(Receipt.status == "verified")
        )
        verified_receipts = verified_receipts.scalar() or 0

        # Выданные призы
        prizes_count = await session.execute(select(func.count(Prize.id)))
        prizes_count = prizes_count.scalar() or 0

        # Выданные призы по типам (для обратной совместимости)
        promo_200_count = await session.execute(
            select(func.count(Prize.id)).where(Prize.discount_amount == 200)
        )
        promo_200_count = promo_200_count.scalar() or 0

        promo_500_count = await session.execute(
            select(func.count(Prize.id)).where(Prize.discount_amount == 500)
        )
        promo_500_count = promo_500_count.scalar() or 0

        return {
            "users_count": users_count,
            "receipts_count": receipts_count,
            "verified_receipts": verified_receipts,
            "prizes_count": prizes_count,
            "promo_200_count": promo_200_count,
            "promo_500_count": promo_500_count,
        }

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return {
            "users_count": 0,
            "receipts_count": 0,
            "verified_receipts": 0,
            "prizes_count": 0,
            "promo_200_count": 0,
            "promo_500_count": 0,
        }


async def get_detailed_admin_stats(session: AsyncSession) -> dict:
    """Получает подробную статистику для админки"""
    try:
        from sqlalchemy import select, func

        # Базовая статистика
        basic_stats = await get_admin_stats(session)

        # Чеки по статусам
        pending_receipts = await session.execute(
            select(func.count(Receipt.id)).where(Receipt.status == "pending")
        )
        pending_receipts = pending_receipts.scalar() or 0

        rejected_receipts = await session.execute(
            select(func.count(Receipt.id)).where(Receipt.status == "rejected")
        )
        rejected_receipts = rejected_receipts.scalar() or 0

        # Использованные призы
        used_prizes = await session.execute(
            select(func.count(Prize.id)).where(Prize.used == True)
        )
        used_prizes = used_prizes.scalar() or 0

        # Суммы чеков
        total_amount = await session.execute(select(func.sum(Receipt.amount)))
        total_amount = total_amount.scalar() or 0

        avg_amount = await session.execute(select(func.avg(Receipt.amount)))
        avg_amount = avg_amount.scalar() or 0

        # Товары Айсида
        total_aisida_items = await session.execute(
            select(func.sum(Receipt.items_count)).where(Receipt.items_count.isnot(None))
        )
        total_aisida_items = total_aisida_items.scalar() or 0

        avg_aisida_items = await session.execute(
            select(func.avg(Receipt.items_count)).where(Receipt.items_count.isnot(None))
        )
        avg_aisida_items = avg_aisida_items.scalar() or 0

        return {
            **basic_stats,
            "pending_receipts": pending_receipts,
            "rejected_receipts": rejected_receipts,
            "used_prizes": used_prizes,
            "total_amount": total_amount,
            "avg_amount": avg_amount,
            "total_aisida_items": total_aisida_items,
            "avg_aisida_items": avg_aisida_items,
        }

    except Exception as e:
        logger.error(f"Ошибка при получении подробной статистики: {str(e)}")
        return await get_admin_stats(session)


def register_admin_handlers():
    """Регистрирует хендлеры админки"""
    return router
