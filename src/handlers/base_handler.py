from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from logger import logger

# Создаем роутер для базовых команд
router = Router()


# Клавиатура главного меню
def get_main_menu_keyboard():
    """
    Создает клавиатуру главного меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Зарегистрировать покупку", callback_data="register_receipt")
    builder.button(text="📦 О продукции «Айсида»", callback_data="about_aisida")
    builder.button(text="📝 Мои чеки", callback_data="my_receipts")
    builder.button(text="🎁 Еженедельный розыгрыш OZON", callback_data="weekly_lottery")
    builder.button(text="🏆 Розыгрыш Главного приза", callback_data="lottery")
    builder.button(text="❓ Частые вопросы", callback_data="faq")
    builder.adjust(1)  # По одной кнопке в ряду
    return builder.as_markup()


def get_start_keyboard():
    """
    Создает клавиатуру для команды /start
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Зарегистрировать покупку", callback_data="register_receipt")
    builder.button(text="Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обрабатывает команду /start
    """
    await message.answer(
        "👋 Добро пожаловать в бот для учета покупок и проверки чеков!\n\n"
        "Здесь вы можете регистрировать свои покупки, проверять чеки "
        "и участвовать в розыгрыше призов.",
        reply_markup=get_start_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обрабатывает команду /help
    """
    help_text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start - Запустить бота и показать главное меню\n"
        "/help - Показать эту справку\n"
        "/menu - Показать главное меню\n\n"
        "<b>Как пользоваться ботом:</b>\n"
        "1. Выберите 'Зарегистрировать покупку' в меню\n"
        "2. Отправьте фото чека или введите данные вручную\n"
        "3. Дождитесь проверки чека\n"
        "4. Получите подарок за покупку\n\n"
        "Если у вас возникли вопросы, выберите 'Частые вопросы' в меню."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """
    Обрабатывает команду /menu
    """
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку возврата в главное меню
    """
    await callback.message.edit_text(
        "Главное меню:", reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "about_aisida")
async def callback_about_aisida(callback: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку "О продукции «Айсида»"
    """
    about_text = (
        "<b>О продукции «Айсида»</b>\n\n"
        "«Айсида» — это серия высококачественных препаратов для здоровья глаз.\n\n"
        "Наши продукты разработаны с использованием передовых технологий "
        "и натуральных компонентов для поддержания здоровья глаз и профилактики "
        "различных офтальмологических заболеваний.\n\n"
        "Подробнее о нашей продукции вы можете узнать на официальном сайте."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Назад в меню", callback_data="main_menu")

    await callback.message.edit_text(
        about_text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "faq")
async def callback_faq(callback: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку "Частые вопросы"
    """
    faq_text = (
        "<b>Часто задаваемые вопросы</b>\n\n"
        "<b>Как зарегистрировать чек?</b>\n"
        "Выберите 'Зарегистрировать покупку' в меню, затем отправьте фото чека "
        "или введите данные вручную.\n\n"
        "<b>Какие данные нужны для регистрации чека?</b>\n"
        "ФН (фискальный номер), ФД (фискальный документ), ФПД (фискальный признак документа) "
        "и сумма покупки.\n\n"
        "<b>Как узнать статус проверки чека?</b>\n"
        "Выберите 'Мои чеки' в главном меню.\n\n"
        "<b>Как получить подарок?</b>\n"
        "После успешной проверки чека вы автоматически получите подарок.\n\n"
        "<b>Как принять участие в розыгрыше?</b>\n"
        "Каждый зарегистрированный и проверенный чек автоматически участвует в розыгрыше."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Назад в меню", callback_data="main_menu")

    await callback.message.edit_text(
        faq_text, reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message, session: AsyncSession):
    """
    Административная команда для просмотра статистики чеков
    """
    # Простая проверка на админа (можно улучшить)
    admin_ids = [123456789]  # Замените на реальные ID администраторов

    if message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        from services.receipt_service import get_receipt_statistics

        # Получаем общую статистику
        stats = await get_receipt_statistics(session)

        if not stats["success"]:
            await message.answer(
                f"❌ Ошибка получения статистики: {stats.get('error')}"
            )
            return

        stats_text = (
            f"📊 <b>Статистика чеков</b>\n\n"
            f"📋 Всего чеков: {stats['total']}\n"
            f"⏳ Ожидают проверки: {stats['pending']}\n"
            f"✅ Подтверждено: {stats['verified']}\n"
            f"❌ Отклонено: {stats['rejected']}\n"
        )

        await message.answer(stats_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в команде admin_stats: {str(e)}")
        await message.answer("❌ Произошла ошибка при получении статистики.")


@router.message(Command("admin_check_pending"))
async def cmd_admin_check_pending(message: Message, session: AsyncSession):
    """
    Административная команда для принудительной проверки всех висящих чеков
    """
    # Простая проверка на админа (можно улучшить)
    admin_ids = [123456789]  # Замените на реальные ID администраторов

    if message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        from services.receipt_service import check_pending_receipts

        # Уведомляем о начале проверки
        status_msg = await message.answer("🔄 Начинаю проверку всех висящих чеков...")

        # Запускаем проверку
        result = await check_pending_receipts(session)

        if not result["success"]:
            await status_msg.edit_text(
                f"❌ Ошибка при проверке чеков: {result.get('error')}"
            )
            return

        # Формируем отчет
        report_text = (
            f"✅ <b>Проверка завершена</b>\n\n"
            f"📋 Обработано чеков: {result['processed']}\n"
            f"✅ Подтверждено: {result['verified']}\n"
            f"❌ Отклонено: {result['rejected']}\n"
        )

        await status_msg.edit_text(report_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в команде admin_check_pending: {str(e)}")
        await message.answer("❌ Произошла ошибка при проверке висящих чеков.")


@router.message(Command("admin_test_status"))
async def cmd_admin_test_status(message: Message, session: AsyncSession):
    """
    Административная команда для тестирования изменения статуса чека
    Формат: /admin_test_status <receipt_id> <new_status>
    """
    # Простая проверка на админа (можно улучшить)
    admin_ids = [123456789]  # Замените на реальные ID администраторов

    if message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        # Парсим аргументы команды
        args = message.text.split()[1:]  # Убираем саму команду

        if len(args) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /admin_test_status <ID_чека> <новый_статус>\n"
                "Например: /admin_test_status 123 verified"
            )
            return

        receipt_id = int(args[0])
        new_status = args[1]

        if new_status not in ["pending", "verified", "rejected"]:
            await message.answer(
                "❌ Неверный статус. Допустимые значения: pending, verified, rejected"
            )
            return

        from services.receipt_service import test_receipt_status_update

        # Уведомляем о начале теста
        status_msg = await message.answer(
            f"🔄 Тестирую изменение статуса чека {receipt_id}..."
        )

        # Запускаем тест
        result = await test_receipt_status_update(session, receipt_id, new_status)

        if not result["success"]:
            await status_msg.edit_text(
                f"❌ Ошибка при тестировании: {result.get('error')}"
            )
            return

        # Формируем отчет
        report_text = (
            f"🧪 <b>Результат теста</b>\n\n"
            f"📋 Чек ID: {receipt_id}\n"
            f"🔄 Старый статус: {result['old_status']}\n"
            f"🎯 Новый статус: {result['new_status']}\n"
            f"✅ Финальный статус: {result['final_status']}\n\n"
            f"📊 Результат: {result['message']}"
        )

        await status_msg.edit_text(report_text, parse_mode="HTML")

    except ValueError:
        await message.answer("❌ ID чека должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в команде admin_test_status: {str(e)}")
        await message.answer("❌ Произошла ошибка при тестировании.")


@router.message(Command("admin_check_receipt"))
async def cmd_admin_check_receipt(message: Message, session: AsyncSession):
    """
    Административная команда для проверки конкретного чека
    Формат: /admin_check_receipt <receipt_id>
    """
    # Простая проверка на админа (можно улучшить)
    admin_ids = [123456789]  # Замените на реальные ID администраторов

    if message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        # Парсим аргументы команды
        args = message.text.split()[1:]  # Убираем саму команду

        if len(args) != 1:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Используйте: /admin_check_receipt <ID_чека>\n"
                "Например: /admin_check_receipt 123"
            )
            return

        receipt_id = int(args[0])

        from services.receipt_service import verify_receipt_with_api
        from sqlalchemy import select
        from models.receipt_model import Receipt

        # Получаем чек для проверки
        receipt_query = await session.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        )
        receipt = receipt_query.scalars().first()

        if not receipt:
            await message.answer(f"❌ Чек с ID {receipt_id} не найден.")
            return

        # Показываем текущую информацию о чеке
        current_info = (
            f"📋 <b>Информация о чеке {receipt_id}</b>\n\n"
            f"👤 Пользователь: {receipt.user_id}\n"
            f"💰 Сумма: {receipt.amount} ₽\n"
            f"📅 Создан: {receipt.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 Текущий статус: <b>{receipt.status}</b>\n"
            f"🕐 Дата проверки: {receipt.verification_date.strftime('%d.%m.%Y %H:%M') if receipt.verification_date else 'Не проверен'}\n"
            f"📦 Товаров Айсида: {receipt.items_count}\n"
            f"🏪 Аптека: {receipt.pharmacy or 'Не указана'}\n\n"
            f"🔄 Запускаю повторную проверку..."
        )

        status_msg = await message.answer(current_info, parse_mode="HTML")

        # Запускаем проверку
        result = await verify_receipt_with_api(session, receipt_id)

        # Получаем обновленную информацию о чеке
        await session.refresh(receipt)

        # Формируем отчет
        if result["success"]:
            report_text = (
                f"✅ <b>Проверка завершена успешно</b>\n\n"
                f"📋 Чек ID: {receipt_id}\n"
                f"📊 Новый статус: <b>{receipt.status}</b>\n"
                f"🕐 Проверен: {receipt.verification_date.strftime('%d.%m.%Y %H:%M')}\n"
                f"📦 Товаров Айсида: {receipt.items_count}\n"
                f"🏪 Аптека: {receipt.pharmacy or 'Не указана'}"
            )
        else:
            report_text = (
                f"❌ <b>Проверка завершена с ошибкой</b>\n\n"
                f"📋 Чек ID: {receipt_id}\n"
                f"📊 Статус: <b>{receipt.status}</b>\n"
                f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
            )

        await status_msg.edit_text(report_text, parse_mode="HTML")

    except ValueError:
        await message.answer("❌ ID чека должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в команде admin_check_receipt: {str(e)}")
        await message.answer("❌ Произошла ошибка при проверке чека.")


def register_base_handlers() -> Router:
    """
    Регистрирует базовые хендлеры и возвращает роутер
    """
    return router
