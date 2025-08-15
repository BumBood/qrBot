import os
from dotenv import load_dotenv
import json
from typing import Optional, Tuple, Dict, Any

# Загрузка переменных окружения из .env файла
load_dotenv()

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройки базы данных
DB_URL = os.getenv("DB_URL")

# Временная админка (для тестов)
ADMIN_PANEL_ENABLED = os.getenv("ADMIN_PANEL_ENABLED", "false").lower() == "true"

# API ФНС
FNC_API_KEY = os.getenv("FNC_API_KEY")
FNC_API_URL = os.getenv("FNC_API_URL", "https://api-fns.ru/api/v1/check")

# API proverkacheka.com
PROVERKACHEKA_API_TOKEN = os.getenv("PROVERKACHEKA_API_TOKEN", "")

# Google Sheets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DEFAULT_GOOGLE_SHEETS_CONFIG_PATH = os.path.abspath(
    os.path.join(PROJECT_ROOT, "data", "google_sheets_config.json")
)


def load_google_sheets_settings() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Загружает настройки Google Sheets.

    Порядок приоритета:
    1) Переменные окружения GOOGLE_SHEETS_CREDENTIALS_JSON и GOOGLE_SHEETS_SPREADSHEET_ID
    2) Файл data/google_sheets_config.json
    """
    credentials_dict: Optional[Dict[str, Any]] = None
    spreadsheet_id: Optional[str] = None

    env_creds = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    env_sheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")

    if env_creds:
        try:
            credentials_dict = json.loads(env_creds)
        except Exception:
            credentials_dict = None
    if env_sheet_id:
        spreadsheet_id = env_sheet_id

    if credentials_dict and spreadsheet_id:
        return credentials_dict, spreadsheet_id

    # Файл
    try:
        if os.path.exists(DEFAULT_GOOGLE_SHEETS_CONFIG_PATH):
            with open(DEFAULT_GOOGLE_SHEETS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                credentials = data.get("credentials_json")
                if isinstance(credentials, str):
                    try:
                        credentials_dict = json.loads(credentials)
                    except Exception:
                        credentials_dict = None
                elif isinstance(credentials, dict):
                    credentials_dict = credentials
                spreadsheet_id = data.get("spreadsheet_id")
    except Exception:
        credentials_dict = None
        spreadsheet_id = None

    return credentials_dict, spreadsheet_id


def save_google_sheets_settings(
    credentials_json_text: str, spreadsheet_id: str
) -> None:
    """Сохраняет настройки Google Sheets в файл data/google_sheets_config.json"""
    os.makedirs(os.path.dirname(DEFAULT_GOOGLE_SHEETS_CONFIG_PATH), exist_ok=True)
    payload = {
        "credentials_json": credentials_json_text,
        "spreadsheet_id": spreadsheet_id,
    }
    with open(DEFAULT_GOOGLE_SHEETS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
