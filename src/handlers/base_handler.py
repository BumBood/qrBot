from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

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


def register_base_handlers() -> Router:
    """
    Регистрирует базовые хендлеры и возвращает роутер
    """
    return router
