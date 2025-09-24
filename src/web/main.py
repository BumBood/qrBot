import os
import datetime
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from database import async_session
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from models.receipt_model import Receipt
from models.user_model import User
from models.promocode_model import Promocode
from models.promo_setting_model import PromoSetting
from config import (
    load_google_sheets_settings,
    save_google_sheets_settings,
)
from services.google_sheets_service import google_sheets_service
from services.lottery_service import select_winner, notify_winner, notify_participants
from services.weekly_lottery_service import WeeklyLotteryService
from services.promocode_service import promocode_service
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from fastapi import HTTPException, status
from models.admin_model import AdminUser
from pathlib import Path
from sqlalchemy import delete as sa_delete
from aiogram import Bot
from aiogram.types import FSInputFile, LinkPreviewOptions
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import BOT_TOKEN
from logger import logger


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_THIS_SECRET_KEY")
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

BROADCAST_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "pics" / "broadcasts"
BROADCAST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def get_current_admin(request: Request) -> AdminUser:
    """Получает текущего аутентифицированного админа из сессии"""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    # Создаем новую сессию для получения админа
    async with async_session() as session:
        admin = await session.get(AdminUser, admin_id)
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return admin


async def get_db():
    async with async_session() as session:
        yield session


@app.get("/admin/receipts", response_class=HTMLResponse)
async def list_receipts(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    status: str = None,
    pharmacy: str = None,
    start_date: str = None,
    end_date: str = None,
    session: AsyncSession = Depends(get_db),
):
    query = select(Receipt)
    if status:
        query = query.where(Receipt.status == status)
    if pharmacy:
        query = query.where(Receipt.pharmacy.ilike(f"%{pharmacy}%"))
    if start_date:
        sd = datetime.datetime.fromisoformat(start_date)
        query = query.where(Receipt.created_at >= sd)
    if end_date:
        ed = datetime.datetime.fromisoformat(end_date)
        query = query.where(Receipt.created_at <= ed)
    query = query.order_by(Receipt.created_at.desc())
    result = await session.execute(query)
    receipts = result.scalars().all()
    return templates.TemplateResponse(
        "receipts.html",
        {
            "request": request,
            "receipts": receipts,
            "filters": {
                "status": status,
                "pharmacy": pharmacy,
                "start_date": start_date,
                "end_date": end_date,
            },
        },
    )


@app.post("/admin/receipts/{receipt_id}/moderate")
async def moderate_receipt(
    receipt_id: int,
    action: str = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    receipt = await session.get(Receipt, receipt_id)
    if receipt and action in ["verified", "rejected"]:
        receipt.status = action
        receipt.verification_date = datetime.datetime.now()
        await session.commit()
    return RedirectResponse(url="/admin/receipts", status_code=303)


@app.get("/admin/receipts/{receipt_id}", response_class=HTMLResponse)
async def receipt_detail(
    request: Request,
    receipt_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    receipt = await session.get(Receipt, receipt_id)
    return templates.TemplateResponse("receipt_detail.html", {"request": request, "receipt": receipt})


@app.get("/admin/lottery", response_class=HTMLResponse)
async def run_main_lottery(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    message = ""
    try:
        winner_id = await select_winner(session)
        if winner_id:
            await notify_winner(session, None, winner_id)
            await notify_participants(session, None, winner_id)
            message = f"Розыгрыш проведён. Победитель: {winner_id}"
        else:
            message = "Розыгрыш проведён. Нет подтверждённых чеков."
    except Exception as e:
        message = f"Ошибка при проведении розыгрыша: {str(e)}"
    return HTMLResponse(content=message)


@app.get("/admin/weekly_lottery")
async def run_weekly_lottery(
    request: Request,
    period: str = "past",
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    result = await WeeklyLotteryService.conduct_lottery(session, for_current_week=(period == "current"))
    if result["success"]:
        if result.get("winner"):
            w = result["winner"]
            message = f"Еженедельная лотерея проведена! Победитель: {w['user_id']}, Чек: {w['receipt_id']}"
        else:
            message = "Еженедельная лотерея проведена. Нет участников."
    else:
        message = f"Ошибка: {result.get('error')}"
    return RedirectResponse(url=f"/admin/users?message={message}", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(User))
    users = result.scalars().all()
    # Получаем количество добавленных чеков для каждого пользователя
    receipt_counts_result = await session.execute(
        select(Receipt.user_id, func.count(Receipt.id)).group_by(Receipt.user_id)
    )
    receipt_counts = {user_id: count for user_id, count in receipt_counts_result.all()}
    utm_counts = {}
    for u in users:
        key = f"{u.utm_source or ''}|{u.utm_medium or ''}|{u.utm_campaign or ''}"
        utm_counts[key] = utm_counts.get(key, 0) + 1
    response = templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": users,
            "utm_counts": utm_counts,
            "receipt_counts": receipt_counts,
        },
    )
    return response


@app.get("/admin/users/utm_export")
async def export_utm_stats(
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    # Получаем пользователей и считаем статистику UTM
    result = await session.execute(select(User))
    users = result.scalars().all()
    utm_counts = {}
    for u in users:
        key = f"{u.utm_source or ''}|{u.utm_medium or ''}|{u.utm_campaign or ''}"
        utm_counts[key] = utm_counts.get(key, 0) + 1

    import io, csv

    output = io.StringIO()
    # Добавляем BOM для корректного открытия в Excel с кодировкой UTF-8
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["utm_source", "utm_medium", "utm_campaign", "count"])
    for utm_str, count in utm_counts.items():
        source, medium, campaign = utm_str.split("|")
        writer.writerow([source, medium, campaign, count])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=utm_stats.csv"},
    )


@app.get("/admin/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/admin/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(AdminUser).where(AdminUser.username == username))
    admin = result.scalars().first()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные логин или пароль"})
    request.session["admin_id"] = admin.id
    return RedirectResponse(url="/admin/receipts", status_code=303)


@app.get("/admin/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


@app.get("/admin/admins", response_class=HTMLResponse)
async def list_admins(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(AdminUser))
    admins = result.scalars().all()
    return templates.TemplateResponse("admins.html", {"request": request, "admins": admins})


@app.post("/admin/admins")
async def create_admin(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    hashed = get_password_hash(password)
    new_admin = AdminUser(username=username, password_hash=hashed)
    session.add(new_admin)
    await session.commit()
    return RedirectResponse(url="/admin/admins", status_code=303)


@app.get("/admin/prizes", response_class=HTMLResponse)
async def list_prizes(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.prize_model import Prize

    result = await session.execute(select(Prize).order_by(Prize.issued_at.desc()))
    prizes = result.scalars().all()
    return templates.TemplateResponse("prizes.html", {"request": request, "prizes": prizes})


@app.get("/admin/lotteries", response_class=HTMLResponse)
async def list_lotteries(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    message: str = None,
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery

    result = await session.execute(select(WeeklyLottery).order_by(WeeklyLottery.created_at.desc()))
    lotteries = result.scalars().all()
    return templates.TemplateResponse(
        "lotteries.html",
        {"request": request, "lotteries": lotteries, "message": message},
    )


@app.get("/admin/promocodes", response_class=HTMLResponse)
async def list_promocodes(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    discount_amount: str = None,
    is_used: str = None,
    is_active: str = None,
    message: str = None,
    session: AsyncSession = Depends(get_db),
):
    """Страница управления промокодами"""

    # Получаем статистику
    stats = await promocode_service.get_promocodes_stats(session)

    # Парсим фильтры
    discount_filter = int(discount_amount) if discount_amount and discount_amount.isdigit() else None
    used_filter = is_used == "true" if is_used else (False if is_used == "false" else None)
    active_filter = is_active == "true" if is_active else (False if is_active == "false" else None)

    # Получаем список промокодов с фильтрацией
    promocodes = await promocode_service.get_promocodes_list(
        session,
        discount_amount=discount_filter,
        is_used=used_filter,
        is_active=active_filter,
        limit=100,
    )

    return templates.TemplateResponse(
        "promocodes.html",
        {
            "request": request,
            "promocodes": promocodes,
            "stats": stats,
            "filters": {
                "discount_amount": discount_amount,
                "is_used": is_used,
                "is_active": is_active,
            },
            "message": message,
        },
    )


@app.post("/admin/promocodes/add")
async def add_promocodes(
    request: Request,
    discount_amount: int = Form(...),
    codes: str = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    """Добавление новых промокодов"""

    # Парсим промокоды из текста
    codes_list = [line.strip() for line in codes.split("\n") if line.strip()]

    if not codes_list:
        return RedirectResponse(
            url="/admin/promocodes?message=Не найдено ни одного промокода",
            status_code=303,
        )

    # Добавляем промокоды через сервис
    result = await promocode_service.add_promocodes(session, codes_list, discount_amount)

    if result["success"]:
        message = f"Добавлено {result['added_count']} промокодов, пропущено {result['skipped_count']}"
    else:
        message = f"Ошибка: {result['error']}"

    return RedirectResponse(url=f"/admin/promocodes?message={message}", status_code=303)


@app.post("/admin/promocodes/{promocode_id}/deactivate")
async def deactivate_promocode(
    promocode_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    """Деактивация промокода"""

    result = await promocode_service.deactivate_promocode(session, promocode_id)

    message = result.get("message", result.get("error", "Неизвестная ошибка"))
    return RedirectResponse(url=f"/admin/promocodes?message={message}", status_code=303)


@app.post("/admin/promocodes/{promocode_id}/activate")
async def activate_promocode(
    promocode_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    """Активация промокода"""

    result = await promocode_service.activate_promocode(session, promocode_id)

    message = result.get("message", result.get("error", "Неизвестная ошибка"))
    return RedirectResponse(url=f"/admin/promocodes?message={message}", status_code=303)


# Новый endpoint для обновления контакта победителя недельного розыгрыша
@app.post("/admin/lotteries/{lottery_id}/update_contact")
async def update_lottery_contact(
    lottery_id: int,
    contact_info: str = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery

    lottery = await session.get(WeeklyLottery, lottery_id)
    if lottery:
        lottery.contact_info = contact_info
        lottery.contact_sent = True
        await session.commit()
    return RedirectResponse(url="/admin/lotteries", status_code=303)


@app.post("/admin/lotteries/{lottery_id}/confirm")
async def confirm_weekly_lottery(
    lottery_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery
    from models.user_model import User
    from services.weekly_lottery_service import WeeklyLotteryService
    from aiogram import Bot
    from config import BOT_TOKEN
    from aiogram.types import FSInputFile
    from sqlalchemy import update as sa_update

    # Определяем корень проекта для абсолютных путей
    BASE_DIR = Path(__file__).resolve().parents[2]

    lottery = await session.get(WeeklyLottery, lottery_id)
    if not lottery or lottery.notification_sent:
        return RedirectResponse(url="/admin/lotteries", status_code=303)

    # Защита от повторной отправки: атомарно помечаем как отправленный ДО рассылки
    upd = await session.execute(
        sa_update(WeeklyLottery)
        .where(WeeklyLottery.id == lottery_id, WeeklyLottery.notification_sent == False)
        .values(notification_sent=True)
    )
    await session.commit()
    if upd.rowcount == 0:
        # Уже был помечен кем-то другим
        return RedirectResponse(url="/admin/lotteries", status_code=303)

    # Отправляем уведомления победителю и участникам
    bot = Bot(token=str(BOT_TOKEN), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    async with bot:
        # Если есть победитель: запрашиваем контактные данные
        if lottery.winner_user_id:
            await WeeklyLotteryService.notify_winner(session, bot, lottery)

        # В любом случае уведомляем всех пользователей о завершении розыгрыша
        # Используем абсолютный путь к файлу картинки
        photo_path = BASE_DIR / "data" / "pics" / "lottery.png"
        lottery_photo = FSInputFile(str(photo_path))
        result = await session.execute(select(User))
        all_users = result.scalars().all()
        # Формируем текст для участников
        if lottery.winner_user_id:
            winner_user = await session.get(User, lottery.winner_user_id)
            winner_mention = f"(@{winner_user.username})" if winner_user and winner_user.username else ""
            participant_caption = (
                "Розыгрыш завершён!\n"
                f"Победитель: чек № {lottery.winner_receipt_id} {winner_mention}.\n"
                "Спасибо за участие! Оставайтесь с «Айсида»"
            )
        else:
            participant_caption = "Розыгрыш завершён!\nУчастников не было.\nСпасибо за участие! Оставайтесь с «Айсида»"
        for user in all_users:
            # Не отправляем победителю повторно
            if lottery.winner_user_id and user.id == lottery.winner_user_id:
                continue

            try:
                await bot.send_photo(
                    user.id,
                    photo=lottery_photo,
                    caption=participant_caption,
                )
            except Exception as e:
                pass
    # Уже помечено выше атомарным апдейтом
    return RedirectResponse(url="/admin/lotteries", status_code=303)


@app.post("/admin/lotteries/{lottery_id}/reroll")
async def reroll_weekly_lottery(
    lottery_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery
    from services.weekly_lottery_service import WeeklyLotteryService
    import random

    lottery = await session.get(WeeklyLottery, lottery_id)
    if not lottery or lottery.notification_sent:
        return RedirectResponse(url="/admin/lotteries", status_code=303)

    # Получаем подходящие чеки недели, исключаем текущий
    receipts = await WeeklyLotteryService.get_eligible_receipts(session, lottery.week_start, lottery.week_end)
    candidates = [r for r in receipts if r.id != lottery.winner_receipt_id]
    if not candidates:
        return RedirectResponse(url="/admin/lotteries", status_code=303)

    winner_receipt = random.choice(candidates)
    lottery.winner_receipt_id = winner_receipt.id
    lottery.winner_user_id = winner_receipt.user_id
    await session.commit()
    return RedirectResponse(url="/admin/lotteries", status_code=303)


@app.post("/admin/lotteries/{lottery_id}/select_winner")
async def select_manual_winner(
    lottery_id: int,
    receipt_id: int = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    """Ручной выбор победителя розыгрыша по номеру чека"""
    from services.weekly_lottery_service import WeeklyLotteryService

    result = await WeeklyLotteryService.manual_select_winner(session, lottery_id, receipt_id)

    if result["success"]:
        message = result["message"]
    else:
        message = result["error"]

    return RedirectResponse(url=f"/admin/lotteries?message={message}", status_code=303)


@app.post("/admin/lotteries/{lottery_id}/delete")
async def delete_weekly_lottery(
    lottery_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery
    from sqlalchemy import delete as sa_delete

    # Удаляем запись через SQL-запрос
    await session.execute(sa_delete(WeeklyLottery).where(WeeklyLottery.id == lottery_id))
    await session.commit()
    return RedirectResponse(url="/admin/lotteries", status_code=303)


@app.get("/admin/settings", response_class=HTMLResponse)
async def settings(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
    message: str = None,
):
    # Получаем текущие настройки промокода акции
    result = await session.execute(select(PromoSetting))
    setting = result.scalars().first()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "setting": setting, "message": message},
    )


@app.post("/admin/settings")
async def update_settings(
    request: Request,
    code: str = Form(...),
    discount_single: int = Form(...),
    discount_multi: int = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    # Обновляем настройки промокода акции
    result = await session.execute(select(PromoSetting))
    setting = result.scalars().first()
    if not setting:
        setting = PromoSetting(
            code=code,
            discount_single=discount_single,
            discount_multi=discount_multi,
        )
        session.add(setting)
    else:
        setting.code = code
        setting.discount_single = discount_single
        setting.discount_multi = discount_multi
    await session.commit()
    message = "Настройки промокода успешно обновлены"
    return RedirectResponse(url=f"/admin/settings?message={message}", status_code=303)


@app.get("/admin/google_sheets", response_class=HTMLResponse)
async def google_sheets_settings(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
):
    creds_dict, sheet_id = load_google_sheets_settings()
    creds_text = ""
    if creds_dict:
        import json

        creds_text = json.dumps(creds_dict, ensure_ascii=False)
    return templates.TemplateResponse(
        "google_sheets.html",
        {
            "request": request,
            "credentials_json": creds_text,
            "spreadsheet_id": sheet_id or "",
        },
    )


@app.post("/admin/google_sheets")
async def save_google_sheets(
    request: Request,
    spreadsheet_id: str = Form(...),
    credentials_json: str = Form(...),
    current_admin: AdminUser = Depends(get_current_admin),
):
    try:
        save_google_sheets_settings(credentials_json, spreadsheet_id)
        message = "Настройки Google Sheets сохранены"
    except Exception as e:
        message = f"Ошибка сохранения настроек: {str(e)}"
    return RedirectResponse(url=f"/admin/google_sheets?message={message}", status_code=303)


@app.get("/admin/google_sheets/test")
async def test_google_sheets(
    current_admin: AdminUser = Depends(get_current_admin),
):
    try:
        client = google_sheets_service.get_client()
        if client is None:
            msg = "Клиент Google Sheets не инициализирован"
        else:
            msg = "Подключение к Google Sheets успешно"
    except Exception as e:
        msg = f"Ошибка подключения: {str(e)}"
    return RedirectResponse(url=f"/admin/google_sheets?message={msg}", status_code=303)


@app.get("/admin/google_sheets/export_now")
async def export_now(
    current_admin: AdminUser = Depends(get_current_admin),
):
    try:
        result = await google_sheets_service.export_users()
        if result.get("success"):
            msg = f"Выгружено пользователей: {result.get('count')}"
        else:
            msg = f"Ошибка выгрузки: {result.get('error')}"
    except Exception as e:
        msg = f"Ошибка выгрузки: {str(e)}"
    return RedirectResponse(url=f"/admin/google_sheets?message={msg}", status_code=303)


@app.post("/admin/receipts/{receipt_id}/delete")
async def delete_receipt(
    receipt_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    try:
        await session.execute(sa_delete(Receipt).where(Receipt.id == receipt_id))
        await session.commit()
        message = f"Чек #{receipt_id} удалён"
    except Exception as e:
        message = f"Ошибка удаления чека #{receipt_id}: {str(e)}"
    return RedirectResponse(url=f"/admin/receipts?message={message}", status_code=303)


# -------------------- Рассылка --------------------
@app.get("/admin/broadcasts", response_class=HTMLResponse)
async def broadcasts_page(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    message: str = None,
):
    return templates.TemplateResponse("broadcasts.html", {"request": request, "message": message})


@app.post("/admin/broadcasts/send")
async def send_broadcast(
    request: Request, html_text: str = Form(...), audience: str = Form("all"), user_ids: str = Form("")
):
    """Отправка рассылки всем или выбранным пользователям.

    - html_text: HTML форматированный текст (parse_mode=HTML)
    - audience: all | specific
    - user_ids: "1,2,3" (если audience=specific)
    - images: multiple files
    """
    from sqlalchemy import select as sa_select

    # Получаем файлы изображений из запроса вручную, так как их может быть несколько
    try:
        form = await request.form()
    except Exception as e:
        err = f"Ошибка разбора формы: {e}"
        logger.error(err)
        return RedirectResponse(url=f"/admin/broadcasts?message={err}", status_code=303)
    image_files = form.getlist("images") if "images" in form else []
    disable_preview = form.get("disable_preview") == "1"

    # Список целевых user_id
    target_ids = []
    async with async_session() as session:
        if audience == "all":
            result = await session.execute(sa_select(User))
            users = result.scalars().all()
            target_ids = [u.id for u in users]
        else:
            # Парсим из строки
            for raw in (user_ids or "").split(","):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    target_ids.append(int(raw))
                except ValueError:
                    logger.warning(f"Пропускаю некорректный user_id: '{raw}'")

    if not target_ids:
        return RedirectResponse(
            url="/admin/broadcasts?message=Не выбран(а) аудитория/пользователи",
            status_code=303,
        )

    # Сохраняем изображения (если есть)
    saved_paths = []
    for f in image_files:
        if isinstance(f, UploadFile):
            try:
                filename = f.filename or "image.jpg"
                safe_name = filename.replace("..", "_")
                dst = BROADCAST_UPLOAD_DIR / safe_name
                # если имя занято — добавим суффикс
                counter = 1
                while dst.exists():
                    stem = dst.stem
                    suffix = dst.suffix
                    dst = BROADCAST_UPLOAD_DIR / f"{stem}_{counter}{suffix}"
                    counter += 1
                content = await f.read()
                with open(dst, "wb") as out:
                    out.write(content)
                saved_paths.append(dst)
            except Exception as e:
                logger.error(f"Ошибка сохранения файла '{getattr(f, 'filename', None)}': {e}")

    # Отправка
    bot = Bot(token=str(BOT_TOKEN), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    sent = 0
    failed = 0
    errors: list[str] = []
    async with bot:
        # Если несколько изображений — отправим альбом по одному пользователю
        for uid in target_ids:
            try:
                if saved_paths:
                    if len(saved_paths) == 1:
                        photo = FSInputFile(str(saved_paths[0]))
                        await bot.send_photo(uid, photo=photo, caption=html_text)
                    else:
                        # Telegram требует медиа-группы; упростим: отправим первое фото с подписью, остальные без подписи
                        first = True
                        for p in saved_paths:
                            photo = FSInputFile(str(p))
                            await bot.send_photo(
                                uid,
                                photo=photo,
                                caption=html_text if first else None,
                            )
                            first = False
                else:
                    await bot.send_message(
                        uid,
                        html_text,
                        link_preview_options=LinkPreviewOptions(is_disabled=True) if disable_preview else None,
                    )
                sent += 1
            except Exception as e:
                failed += 1
                err_text = f"uid={uid}: {e.__class__.__name__}: {e}"
                errors.append(err_text)
                logger.error(f"Ошибка отправки рассылки {err_text}")

    details = ""
    if errors:
        preview = " | ".join(errors[:3])
        details = f"; детали: {preview}"
    msg = f"Рассылка завершена. Успешно: {sent}, ошибок: {failed}{details}"
    return RedirectResponse(url=f"/admin/broadcasts?message={msg}", status_code=303)
