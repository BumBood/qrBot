import os
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from models.receipt_model import Receipt
from services.receipt_service import (
    process_receipt_photo,
    process_manual_receipt,
    verify_receipt_with_api,
)
from services.prize_service import issue_prize
from logger import logger
from handlers.base_handler import get_main_menu_keyboard

# Создаем роутер для работы с чеками
router = Router()


# Состояния для FSM
class ReceiptStates(StatesGroup):
    waiting_for_photo = State()  # Ожидание фото чека
    waiting_for_fn = State()  # Ожидание ввода ФН
    waiting_for_receipt_number = State()  # Ожидание ввода номера чека


# Клавиатура выбора метода ввода чека
def get_receipt_method_keyboard():
    """
    Создает клавиатуру выбора метода ввода чека
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить фото чека", callback_data="receipt_photo")
    builder.button(text="Ввести данные вручную", callback_data="receipt_manual")
    builder.button(text="Назад в меню", callback_data="main_menu")
    builder.adjust(1)  # По одной кнопке в ряду
    return builder.as_markup()


# Клавиатура для возврата в меню
def get_back_keyboard():
    """
    Создает клавиатуру с кнопкой возврата в меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад в меню", callback_data="main_menu")
    return builder.as_markup()


@router.message(Command("register"))
async def cmd_register(message: Message, state: FSMContext):
    """
    Обрабатывает команду /register
    """
    await message.answer(
        "Выберите способ регистрации чека:", reply_markup=get_receipt_method_keyboard()
    )


@router.callback_query(F.data == "register_receipt")
async def callback_register_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку "Зарегистрировать покупку"
    """
    await callback.message.edit_text(
        "Выберите способ регистрации чека:", reply_markup=get_receipt_method_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "receipt_photo")
async def callback_receipt_photo(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор метода "Отправить фото чека"
    """
    await callback.message.edit_text(
        "Пожалуйста, отправьте фотографию чека. "
        "На фото должен быть четко виден QR-код чека.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(ReceiptStates.waiting_for_photo)
    await callback.answer()


@router.message(F.photo, ReceiptStates.waiting_for_photo)
async def process_photo(message: Message, state: FSMContext, session: AsyncSession):
    """
    Обрабатывает полученное фото чека (сценарий как на скриншоте)
    """
    photo = message.photo[-1]
    os.makedirs("temp", exist_ok=True)
    photo_path = f"temp/{photo.file_id}.jpg"

    try:
        # Загружаем фото
        await message.bot.download(photo, destination=photo_path)
        user_id = message.from_user.id

        # 1. Получаем данные чека с фото
        result = await process_receipt_photo(user_id, photo_path)

        # Удаляем временный файл
        try:
            if os.path.exists(photo_path):
                os.remove(photo_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении временного файла: {str(e)}")

        if not result["success"]:
            await message.answer(
                f"❌ Не удалось распознать QR-код: {result.get('error', 'Неизвестная ошибка')}\n"
                f"Пожалуйста, убедитесь, что QR-код хорошо виден на фото, или введите данные вручную.",
                reply_markup=get_receipt_method_keyboard(),
            )
            await state.clear()
            return

        # 2. Сохраняем данные чека в БД
        receipt_result = await process_manual_receipt(
            session,
            user_id,
            result["fn"],
            result["fd"],
            result["fpd"],
            result["amount"],
        )
        if not receipt_result["success"]:
            await message.answer(
                f"❌ Ошибка при регистрации чека: {receipt_result.get('error', 'Неизвестная ошибка')}\n"
                f"Пожалуйста, попробуйте еще раз.",
                reply_markup=get_receipt_method_keyboard(),
            )
            await state.clear()
            return

        # 3. Промежуточное сообщение о проверке через API
        wait_msg = await message.answer(
            "Проверяю чек через API... ⏳\n\nБот выполняет запрос"
        )

        # 4. Проверяем чек через API
        verify_result = await verify_receipt_with_api(
            session, receipt_result["receipt_id"]
        )

        if not verify_result["success"]:
            # Чек отклонен - выводим подробную информацию
            error_message = verify_result.get("error", "Неизвестная ошибка")

            builder = InlineKeyboardBuilder()
            builder.button(text="Попробовать снова", callback_data="receipt_photo")
            builder.button(text="Ввести данные вручную", callback_data="receipt_manual")
            builder.button(text="Назад в меню", callback_data="main_menu")
            builder.adjust(1)

            await wait_msg.edit_text(
                f"❌ <b>Чек отклонен</b>\n\n"
                f"Причина: {error_message}\n\n"
                f"Проверьте правильность данных чека и попробуйте снова. "
                f"Статус чека автоматически изменен на 'отклонен'.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
            await state.clear()
            return

        # 5. Чек валиден — подробный отчёт
        # Достаём подробности для сообщения
        pharmacy = verify_result.get("pharmacy", "Аптека неизвестна")
        address = verify_result.get("address", "Адрес неизвестен")
        date = verify_result.get("date", "Дата неизвестна")
        aisida_count = verify_result.get("aisida_count", 0)
        aisida_items = verify_result.get("aisida_items", [])  # список строк
        items_str = (
            "\n".join(f"({item})" for item in aisida_items) if aisida_items else "-"
        )

        # Выдаём подарок в зависимости от количества товаров
        prize_result = await issue_prize(
            session, receipt_result["receipt_id"], aisida_count
        )

        # Формируем подробный текст
        text = (
            f"✅ Чек подтверждён!\n"
            f"Аптека: {pharmacy}, {address}\n"
            f"Дата/время: {date}\n\n"
            f"В чеке найдены <b>{aisida_count} позиции «Айсида»</b>.\n"
            f"{items_str}\n\n"
        )

        if prize_result["success"]:
            discount = prize_result["discount_amount"]
            code = prize_result["code"]
            text += f"🎁 <b>Ваш подарок: промокод на скидку {discount} руб.</b>\n"
            text += f"Промокод: <code>{code}</code>\n"
            text += f"Действует на продукцию Айсида на OZON\n\n"
            text += f"<i>Промокод можно использовать только один раз.</i>\n"
        else:
            text += f"❌ {prize_result.get('error', 'Произошла ошибка при выдаче подарка')}\n"

        await wait_msg.edit_text(
            text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке фото чека: {str(e)}")

        # Удаляем временный файл в случае ошибки
        try:
            if os.path.exists(photo_path):
                os.remove(photo_path)
        except Exception as file_error:
            logger.error(f"Ошибка при удалении временного файла: {str(file_error)}")

        await message.answer(
            "Произошла ошибка при обработке фото чека. Пожалуйста, попробуйте еще раз или введите данные вручную.",
            reply_markup=get_receipt_method_keyboard(),
        )

    finally:
        # Очищаем состояние в любом случае
        await state.clear()


@router.callback_query(F.data == "receipt_manual")
async def callback_receipt_manual(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор метода "Ввести данные вручную"
    """
    await callback.message.edit_text(
        "Введите данные чека в формате:\n"
        "ФН ФД ФПД СУММА\n"
        "Например: 8710000101234567 1234 5678901234 299.50",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(ReceiptStates.waiting_for_fn)
    await callback.answer()


def get_manual_entry_keyboard():
    """
    Клавиатура для ошибок ручного ввода: Попробовать снова, Отправить фото, Назад в меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Попробовать снова", callback_data="receipt_manual")
    builder.button(text="Отправить фото чека", callback_data="receipt_photo")
    builder.button(text="Назад в меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.message(ReceiptStates.waiting_for_fn)
async def process_manual_entry(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Обрабатывает однострочный ручной ввод чека
    """
    try:
        text = message.text.strip().replace(",", ".")
        parts = text.split()
        if len(parts) != 4:
            await message.answer(
                "Данные введены неверно. Убедитесь, что ФН (16 или 17 цифр), ФД (4–6 цифр), ФПД (10 цифр) и сумма (xxx.xx), разделённые пробелом.\n"
                "Попробуйте снова или пришлите фото чека.",
                reply_markup=get_manual_entry_keyboard(),
            )
            await state.clear()
            return

        fn, fd, fpd, amount = parts
        if (
            not re.match(r"^\d{16,17}$", fn)
            or not re.match(r"^\d{4,6}$", fd)
            or not re.match(r"^\d{10}$", fpd)
            or not re.match(r"^\d+\.\d{2}$", amount)
        ):
            await message.answer(
                "Данные введены неверно. Убедитесь, что ФН (16 или 17 цифр), ФД (4–6 цифр), ФПД (10 цифр) и сумма (xxx.xx), разделённые пробелом.\n"
                "Попробуйте снова или пришлите фото чека.",
                reply_markup=get_manual_entry_keyboard(),
            )
            await state.clear()
            return

        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("Сумма должна быть положительной")
        except Exception as e:
            logger.error(f"Ошибка при преобразовании суммы: {str(e)}")
            await message.answer(
                "Данные введены неверно. Убедитесь, что сумма указана в формате xxx.xx.\n"
                "Попробуйте снова или пришлите фото чека.",
                reply_markup=get_manual_entry_keyboard(),
            )
            await state.clear()
            return

        user_id = message.from_user.id

        # Сообщение о проверке
        wait_msg = await message.answer("Проверяю данные чека... ⏳")

        # Сохраняем данные чека в БД
        receipt_result = await process_manual_receipt(
            session, user_id, fn, fd, fpd, amount_val
        )

        if not receipt_result["success"]:
            await wait_msg.edit_text(
                f"❌ Ошибка при регистрации чека: {receipt_result.get('error', 'Неизвестная ошибка')}\n"
                f"Пожалуйста, попробуйте еще раз.",
                reply_markup=get_manual_entry_keyboard(),
            )
            await state.clear()
            return

        # Проверяем чек через API
        verify_result = await verify_receipt_with_api(
            session, receipt_result["receipt_id"]
        )

        if not verify_result["success"]:
            error_message = verify_result.get("error", "Неизвестная ошибка")
            await wait_msg.edit_text(
                f"❌ <b>Чек отклонен</b>\n\n"
                f"Причина: {error_message}\n\n"
                f"Статус чека автоматически изменен на 'отклонен'. "
                f"Пожалуйста, проверьте данные и попробуйте еще раз.",
                reply_markup=get_manual_entry_keyboard(),
                parse_mode="HTML",
            )
            await state.clear()
            return

        # Выдаём подарок в зависимости от количества товаров
        aisida_count = verify_result.get("aisida_count", 0)
        prize_result = await issue_prize(
            session, receipt_result["receipt_id"], aisida_count
        )

        # Формируем ответ
        if prize_result["success"]:
            discount = prize_result["discount_amount"]
            code = prize_result["code"]
            await wait_msg.edit_text(
                f"✅ Чек успешно проверен!\n\n"
                f"Сумма: {amount_val} руб.\n"
                f"Количество товаров «Айсида»: {aisida_count}\n\n"
                f"🎁 <b>Ваш подарок: промокод на скидку {discount} руб.</b>\n"
                f"Промокод: <code>{code}</code>\n"
                f"Действует на продукцию Айсида на OZON\n\n"
                f"<i>Промокод можно использовать только один раз.</i>\n\n"
                f"Спасибо за покупку!",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML",
            )
        else:
            await wait_msg.edit_text(
                f"✅ Чек успешно проверен!\n\n"
                f"Сумма: {amount_val} руб.\n"
                f"Количество товаров «Айсида»: {aisida_count}\n\n"
                f"❌ {prize_result.get('error', 'Произошла ошибка при выдаче подарка')}\n",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Ошибка при обработке ручного ввода чека: {str(e)}")
        await message.answer(
            "Произошла ошибка при обработке данных чека. Пожалуйста, попробуйте еще раз.",
            reply_markup=get_manual_entry_keyboard(),
        )

    finally:
        # Очищаем состояние в любом случае
        await state.clear()


@router.callback_query(F.data == "my_receipts")
async def callback_my_receipts(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    """
    Обрабатывает нажатие на кнопку "Мои чеки"
    """
    user_id = callback.from_user.id

    # Получаем последние 3 чека пользователя, включая призы
    receipts_query = await session.execute(
        select(Receipt)
        .options(selectinload(Receipt.prizes))
        .where(Receipt.user_id == user_id)
        .order_by(Receipt.created_at.desc())
        .limit(3)
    )
    receipts = receipts_query.scalars().all()

    builder = InlineKeyboardBuilder()
    builder.button(text="Ввести номер", callback_data="enter_receipt_number")
    builder.button(text="Меню", callback_data="main_menu")
    builder.adjust(1)

    if not receipts:
        await callback.message.edit_text(
            "У вас пока нет зарегистрированных чеков.",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    # Формируем список чеков
    receipts_text = "<b>Ваши последние регистрации:</b>\n\n"

    for i, receipt in enumerate(receipts, 1):
        status_text = ""
        if receipt.status == "verified":
            status_text = "Подтверждён"
            if receipt.prizes:
                prize = receipt.prizes[0]
                status_text += f", подарок: промокод {prize.discount_amount} ₽"
        elif receipt.status == "pending":
            status_text = "Ожидает проверки"
        elif receipt.status == "rejected":
            status_text = "Отклонён ❌"
        else:
            status_text = "Неизвестный статус"

        receipts_text += (
            f"{i}. № {receipt.id} ({receipt.created_at.strftime('%d.%m.%Y')}) — "
            f"{status_text}\n"
        )

    receipts_text += "\nДля подробностей введите номер регистрации или нажмите «Меню»."

    await callback.message.edit_text(
        receipts_text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await state.set_state(ReceiptStates.waiting_for_receipt_number)
    await callback.answer()


@router.callback_query(
    F.data == "enter_receipt_number", ReceiptStates.waiting_for_receipt_number
)
async def callback_enter_receipt_number(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку "Ввести номер"
    """
    await callback.message.edit_text(
        "Введите номер регистрации чека:",
        reply_markup=get_back_to_my_receipts_keyboard(),
    )
    await callback.answer()


def get_back_to_my_receipts_keyboard():
    """
    Создает клавиатуру с кнопками 'Мои чеки' и 'Меню' для возврата
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Мои чеки", callback_data="my_receipts")
    builder.button(text="Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.message(ReceiptStates.waiting_for_receipt_number)
async def process_receipt_number(
    message: Message, state: FSMContext, session: AsyncSession
):
    """
    Обрабатывает ввод номера чека для просмотра деталей
    """
    receipt_id_str = message.text.strip()
    if not receipt_id_str.isdigit():
        await message.answer(
            "❌ Неверный формат номера. Пожалуйста, введите число.",
            reply_markup=get_back_to_my_receipts_keyboard(),
        )
        return

    receipt_id = int(receipt_id_str)
    user_id = message.from_user.id

    receipt_query = await session.execute(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    )
    receipt = receipt_query.scalar_one_or_none()

    if not receipt:
        await message.answer(
            "❌ Чек с таким номером не найден или не принадлежит вам.",
            reply_markup=get_back_to_my_receipts_keyboard(),
        )
        return

    status_text = ""
    status_emoji = ""
    if receipt.status == "verified":
        status_text = "Подтверждён"
        status_emoji = "✅"
    elif receipt.status == "pending":
        status_text = "Ожидает проверки"
        status_emoji = "⏳"
    elif receipt.status == "rejected":
        status_text = "Отклонён"
        status_emoji = "❌"
    else:
        status_text = "Неизвестный статус"
        status_emoji = "❓"

    # Формируем подробную информацию о чеке
    verification_info = ""
    if receipt.verification_date:
        verification_info = (
            f" (проверен {receipt.verification_date.strftime('%d.%m.%Y %H:%M')})"
        )

    receipt_details_text = (
        f"<b>Регистрация № {receipt.id}</b>\n\n"
        f"📅 Дата регистрации: {receipt.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"💰 Сумма: {receipt.amount} ₽\n"
        f"🏪 Аптека: {receipt.pharmacy if receipt.pharmacy else 'Не указана'}\n"
        f"📦 Найдено товаров «Айсида»: {receipt.items_count}\n\n"
        f"📋 Статус: {status_emoji} <b>{status_text}</b>{verification_info}\n"
    )

    # Добавляем информацию о подарке, если есть
    # Ищем связанный подарок через модель Prize (если она существует)
    # Пока оставим базовую проверку
    if receipt.status == "verified" and receipt.items_count > 0:
        receipt_details_text += f"\n🎁 За этот чек вы получили подарок!"

    await message.answer(
        receipt_details_text,
        reply_markup=get_back_to_my_receipts_keyboard(),
        parse_mode="HTML",
    )
    await state.clear()


def register_receipt_handlers() -> Router:
    """
    Регистрирует хендлеры для работы с чеками и возвращает роутер
    """
    return router
