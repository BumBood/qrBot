import os
import datetime
from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import async_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.receipt_model import Receipt
from models.user_model import User
from models.promocode_model import Promocode
from services.lottery_service import select_winner, notify_winner, notify_participants
from services.weekly_lottery_service import WeeklyLotteryService
from services.promocode_service import promocode_service
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext
from fastapi import HTTPException, status
from models.admin_model import AdminUser

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_THIS_SECRET_KEY")
BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def get_current_admin(request: Request) -> AdminUser:
    """Получает текущего аутентифицированного админа из сессии"""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"}
        )
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
    return templates.TemplateResponse(
        "receipt_detail.html", {"request": request, "receipt": receipt}
    )


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
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    result = await WeeklyLotteryService.conduct_lottery(session)
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
    utm_counts = {}
    for u in users:
        key = u.utm or ""
        utm_counts[key] = utm_counts.get(key, 0) + 1
    return templates.TemplateResponse(
        "users.html", {"request": request, "users": users, "utm_counts": utm_counts}
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
    result = await session.execute(
        select(AdminUser).where(AdminUser.username == username)
    )
    admin = result.scalars().first()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неверные логин или пароль"}
        )
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
    return templates.TemplateResponse(
        "admins.html", {"request": request, "admins": admins}
    )


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
    return templates.TemplateResponse(
        "prizes.html", {"request": request, "prizes": prizes}
    )


@app.get("/admin/lotteries", response_class=HTMLResponse)
async def list_lotteries(
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db),
):
    from models.weekly_lottery_model import WeeklyLottery

    result = await session.execute(
        select(WeeklyLottery).order_by(WeeklyLottery.created_at.desc())
    )
    lotteries = result.scalars().all()
    return templates.TemplateResponse(
        "lotteries.html", {"request": request, "lotteries": lotteries}
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
    discount_filter = (
        int(discount_amount) if discount_amount and discount_amount.isdigit() else None
    )
    used_filter = (
        is_used == "true" if is_used else (False if is_used == "false" else None)
    )
    active_filter = (
        is_active == "true" if is_active else (False if is_active == "false" else None)
    )

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
    result = await promocode_service.add_promocodes(
        session, codes_list, discount_amount
    )

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
