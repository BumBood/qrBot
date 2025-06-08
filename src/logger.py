import logging
from logging.handlers import RotatingFileHandler
import os
import sys


def setup_logger() -> logging.Logger:
    """
    Настраивает и возвращает логгер с ротацией файлов
    """
    # Создаем директорию для логов, если она не существует
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Настраиваем логгер
    logger = logging.getLogger("qr_bot")
    logger.setLevel(logging.INFO)

    # Форматтер для логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Обработчик для вывода в файл с ротацией
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bot.log"), maxBytes=10485760, backupCount=5  # 10 MB
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Создаем экземпляр логгера
logger = setup_logger()


def log_error(error: Exception) -> None:
    """
    Логирует ошибку с полным контекстом
    """
    logger.error(f"Произошла ошибка: {str(error)}", exc_info=True)
