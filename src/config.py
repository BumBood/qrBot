import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройки базы данных
DB_URL = os.getenv("DB_URL")

# API ФНС
FNC_API_KEY = os.getenv("FNC_API_KEY")
FNC_API_URL = os.getenv("FNC_API_URL", "https://api-fns.ru/api/v1/check")

# ID администраторов
ADMIN_IDS = (
    list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
    if os.getenv("ADMIN_IDS")
    else []
)
