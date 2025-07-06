from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from models.user_model import User
from logger import logger
from sqlalchemy import select
from models.promo_setting_model import PromoSetting

# Создаем роутер для базовых команд
router = Router()


# Клавиатура главного меню
def get_main_menu_keyboard():
    """
    Создает клавиатуру главного меню
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="1. Зарегистрировать покупку", callback_data="register_receipt")
    builder.button(text="2. Мои чеки", callback_data="my_receipts")
    builder.button(text="3. О продукции «Айсида»", callback_data="about_aisida")
    builder.button(text="4. Розыгрыш Главного приза", callback_data="weekly_lottery")
    builder.button(text="5. Частые вопросы", callback_data="faq")
    builder.adjust(1)  # По одной кнопке в ряду
    return builder.as_markup()


def get_start_keyboard():
    """
    Создает клавиатуру для команды /start
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Зарегистрировать покупку", callback_data="register_receipt")
    builder.button(text="Меню", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession):
    """
    Обрабатывает команду /start
    """
    # Получаем настройки промокода акции
    result = await session.execute(select(PromoSetting))
    setting = result.scalars().first()
    code = setting.code if setting else "ЛЕТО_КРАСОТЫ"
    # Текст приветствия и инструкции по акции
    message_text = (
        "<b>Ваша скидка при покупке:</b>\n"
        f"• {setting.discount_single} ₽ при покупке <b>1</b> средства «Айсида»\n"
        f"• {setting.discount_multi} ₽ при покупке <b>2 и более</b> средств «Айсида»\n\n"
        f"Используйте промо-код <b>{code}</b> при заказе товара:\n"
        '• на сайте <a href="https://planetazdorovo.ru/search/?sort=sort&q=%D0%90%D0%B9%D1%81%D0%B8%D0%B4%D0%B0&appointments=&is_favorite_store=&product_price_min=148&product_price_max=1089&brand%5B%5D=1322&set_filter=Y">«Планета Здоровья»</a>\n\n'
        "<i>* Скидка по промо-коду применяется сразу в момент покупки.*</i>\n\n"
        f"Получите бережный уход за кожей по специальной цене с промо-кодом <b>{code}</b> и участвуйте в еженедельном розыгрыше сертификата <b>OZON на 5 000 ₽</b>!\n\n"
        "<b>Как участвовать в еженедельном розыгрыше сертификата OZON на 5 000 ₽:</b>\n"
        "1. После выкупа товара нажмите в меню <b>«Зарегистрировать покупку»</b>.\n"
        "2. Сфотографируйте чек или введите данные чека вручную.\n"
        "3. Вы автоматически попадёте в розыгрыш сертификата OZON на <b>5 000 ₽</b>, который проходит <b>каждый понедельник</b>.\n\n"
        "<b>Готовы начать?</b>\n"
        "Нажмите <b>«Зарегистрировать покупку»</b> или выберите <b>«Меню»</b>, чтобы узнать больше."
    )
    await message.answer(message_text, reply_markup=get_start_keyboard())


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
        "В акции участвуют средства линейки «Айсида», представленные в аптечной сети «Планета Здоровья».\n\n"
        "<b>1. Пенка для умывания «Айсида»</b>\n"
        "Мягко очищает сухую и чувствительную кожу, не нарушая её естественный гидробаланс. Обеспечивает длительное увлажнение и восстанавливает барьерные свойства за счёт комплекса натуральных экстрактов и АСД. Идеальна для ежедневного ухода и подготовки кожи к дальнейшим этапам ухода.\n"
        "🔗 Подробнее: https://avzpharm.ru/ajsida/katalog/#penka\n\n"
        "<b>2. Крем для сухой и чувствительной кожи лица и тела «Айсида» (50 мл) или (250 мл)</b>\n"
        "Интенсивно питает и увлажняет, устраняет покраснения и раздражение благодаря 98 % натуральным ингредиентам с маслами липы, лаванды и АСД. Восстанавливает гидролипидный баланс и возвращает ощущение комфорта даже после агрессивных процедур. Подходит для ежедневного применения утром и вечером.\n"
        "🔗 Подробнее о креме: https://avzpharm.ru/ajsida/katalog/#cream-face-body\n\n"
        "<b>3. Крем для жирной и комбинированной кожи лица и тела «Айсида» (50 мл)</b>\n"
        "Нормализует гидролипидный баланс и препятствует появлению несовершенств благодаря АСД, маслу сладкого миндаля и экстрактам овса и василька. Оказывает противовоспалительное действие, ускоряет заживление без рубцов и помогает контролировать работу сальных желёз. Формула на 97 % натуральна, не содержит гормонов, парабенов, синтетических красителей и силиконов.\n"
        "🔗 Подробнее о креме: https://avzpharm.ru/ajsida/katalog/krem-dlya-zhirnoj-i-kombinirovannoj-kozhi/\n\n"
        "<b>4. Шампунь «Айсида» с АСД для всех типов волос (250 мл)</b>\n"
        "Эффективно устраняет зуд и шелушение, укрепляет корни и защищает от перхоти без парабенов и отдушек. Липосомальная форма АСД глубоко проникает в кожу головы, восстанавливая её естественный баланс. Рекомендуется для людей, страдающих себореей, выпадением волос и возрастными изменениями.\n"
        "🔗 Подробнее о шампуне: https://avzpharm.ru/ajsida/katalog/#shampoo\n\n"
        "<b>5. Бальзам-маска для сухой кожи головы «Айсида» (250 мл)</b>\n"
        "Идеальный компаньон к шампуню «Айсида» при себорейном дерматите, псориазе кожи головы, а также при обычной сухости и шелушении. В составе 98 % натуральных ингредиентов, включая масла репейника и оливы, АСД и эфирные масла лаванды и лимонника, что позволяет одновременно успокаивать раздражённую кожу, глубоко её питать и препятствовать образованию перхоти. При сочетании с противогрибковых шампунями (кетоконазол) бальзам-маска усиливает их терапевтический эффект и помогает ускорить восстановление.\n"
        "🔗 Подробнее о бальзам-маске: https://avzpharm.ru/ajsida/katalog/#balm-mask\n\n"
        "<b>6. Крем для ног «Айсида» с АСД и мочевиной 30 % (50 мл)</b>\n"
        "Специальная формула интенсивно увлажняет и смягчает грубую и утолщённую кожу стоп, деликатно отшелушивая натоптыши и мозоли. Способствует заживлению микротравм и восстановлению гидролипидного слоя благодаря сочетанию мочевины и АСД. Лёгкая текстура быстро впитывается и не оставляет следов.\n"
        "🔗 Подробнее: https://avzpharm.ru/ajsida/katalog/#foot-cream\n\n"
        "Чтобы вернуться в меню, нажмите «Меню».\n"
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
        "1. <b>Как зарегистрировать чек?</b>\n"
        "Выберите <b>«Зарегистрировать покупку»</b> в меню, затем отправьте фото чека или введите данные вручную.\n\n"
        "2. <b>Какие данные нужны для регистрации чека?</b>\n"
        "ФН (фискальный номер), ФД (фискальный документ), ФПД (фискальный признак документа) и сумма покупки.\n\n"
        "3. <b>Почему мой чек не распознаётся?</b>\n"
        "– Фотографируйте QR-код без бликов, при хорошем освещении.\n"
        "– Если не выходит — введите данные чека вручную.\n\n"
        "4. <b>Как узнать статус чека?</b>\n"
        "– «Подтверждён ✅» отображается в разделе «Мои чеки».\n"
        "– «Ожидает проверки» означает, что бот запрашивает данные у ФНС.\n\n"
        "5. <b>Почему чек может быть отклонён?</b>\n"
        "– Вероятнее всего, сумма или реквизиты не совпали с данными ФНС. Проверьте правильность ввода.\n\n"
        "6. <b>Как использовать промокод?</b>\n"
        "– Предоставьте его при оформлении заказа на сайте «Планета Здоровья».\n\n"
        "7. <b>Где узнать правила акции?</b>\n"
        'Правила акции размещены на сайте <a href="https://avzpharm.ru/">avzpharm.ru</a>'
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="Меню", callback_data="main_menu")

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
