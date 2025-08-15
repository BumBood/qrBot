import asyncio
from typing import List, Optional, Any

import gspread  # type: ignore
from google.oauth2.service_account import Credentials  # type: ignore

from database import async_session
from sqlalchemy import select
from models.user_model import User
from logger import logger
from config import load_google_sheets_settings


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsService:
    def __init__(self) -> None:
        self._client: Optional[gspread.Client] = None

    def _build_client(self) -> Optional[gspread.Client]:
        try:
            credentials_dict, _ = load_google_sheets_settings()
            if not credentials_dict:
                logger.warning(
                    "Учетные данные Google Sheets не заданы — экспорт отключен"
                )
                return None
            credentials = Credentials.from_service_account_info(
                credentials_dict, scopes=SCOPES
            )
            return gspread.authorize(credentials)
        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}")
            return None

    def get_client(self) -> Optional[gspread.Client]:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def export_users(self) -> dict:
        try:
            # Сначала читаем данные из БД в текущем event loop
            users_data: List[List[str]] = []
            async with async_session() as session:
                res = await session.execute(select(User))
                users: List[User] = res.scalars().all()
                for u in users:
                    users_data.append(
                        [
                            str(u.id or ""),
                            (
                                str(u.username)
                                if getattr(u, "username", None) is not None
                                else ""
                            ),
                            (
                                str(u.full_name)
                                if getattr(u, "full_name", None) is not None
                                else ""
                            ),
                            (
                                str(u.utm_source)
                                if getattr(u, "utm_source", None) is not None
                                else ""
                            ),
                            (
                                str(u.utm_medium)
                                if getattr(u, "utm_medium", None) is not None
                                else ""
                            ),
                            (
                                str(u.utm_campaign)
                                if getattr(u, "utm_campaign", None) is not None
                                else ""
                            ),
                            (
                                u.registered_at.strftime("%Y-%m-%d %H:%M:%S")
                                if u.registered_at
                                else ""
                            ),
                        ]
                    )

            # Затем выполняем блокирующие операции gspread в отдельном потоке
            loop = asyncio.get_running_loop()

            def _export_sync(data: List[List[str]]) -> dict:
                _, spreadsheet_id = load_google_sheets_settings()
                if not spreadsheet_id:
                    return {"success": False, "error": "Не задан Spreadsheet ID"}

                client = self._build_client()
                if client is None:
                    return {
                        "success": False,
                        "error": "Клиент Google Sheets недоступен",
                    }

                sh = client.open_by_key(spreadsheet_id)
                try:
                    ws = sh.worksheet("Пользователи")
                except gspread.WorksheetNotFound:
                    ws = sh.add_worksheet(title="Пользователи", rows=1000, cols=10)

                headers = [
                    "telegram_id",
                    "username",
                    "full_name",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "registered_at",
                ]

                ws.clear()
                ws.update("A1", [headers])
                if data:
                    ws.update("A2", data)

                return {"success": True, "count": len(data)}

            result = await loop.run_in_executor(None, _export_sync, users_data)
            return result
        except Exception as e:
            logger.error(f"Ошибка экспорта пользователей в Google Sheets: {e}")
            return {"success": False, "error": str(e)}


google_sheets_service = GoogleSheetsService()
