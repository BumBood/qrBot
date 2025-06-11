import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import inspect
import traceback
import functools
from typing import Callable, TypeVar, Any, ParamSpec, Optional, ContextManager
from contextlib import contextmanager

P = ParamSpec("P")
T = TypeVar("T")


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


def log_error(error: Exception, stack_level: int = 1) -> None:
    """
    Логирует ошибку с полным контекстом, включая информацию о функции,
    в которой произошла ошибка

    Args:
        error: Исключение для логирования
        stack_level: Уровень стека для определения места вызова (по умолчанию 1 - вызывающая функция)
    """
    # Получаем информацию о стеке вызовов
    stack = inspect.stack()
    if stack_level < len(stack):
        frame_info = stack[stack_level]
        function_name = frame_info.function
        file_name = frame_info.filename
        line_number = frame_info.lineno

        error_location = (
            f"Файл: {file_name}, Функция: {function_name}, Строка: {line_number}"
        )
    else:
        error_location = "Информация о месте вызова недоступна"

    # Добавляем полный стек вызовов для более детального анализа
    stack_trace = "".join(traceback.format_tb(error.__traceback__))

    logger.error(
        f"Произошла ошибка: {str(error)} | {error_location}\nСтек вызовов:\n{stack_trace}"
    )


def log_exceptions(func: Callable[P, T]) -> Callable[P, T]:
    """
    Декоратор для автоматического логирования исключений в функциях

    Args:
        func: Декорируемая функция

    Returns:
        Обернутая функция с логированием исключений
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Используем stack_level=2, чтобы получить информацию о функции,
            # в которой произошла ошибка, а не о wrapper
            log_error(e, stack_level=2)
            raise  # Повторно вызываем исключение после логирования

    return wrapper


@contextmanager
def error_logging_context(context_name: Optional[str] = None) -> ContextManager[None]:
    """
    Контекстный менеджер для логирования ошибок в блоке кода

    Args:
        context_name: Опциональное название контекста для более информативных логов

    Yields:
        None

    Example:
        ```python
        with error_logging_context("Обработка платежа"):
            # код, который может вызвать исключение
            process_payment(payment_data)
        ```
    """
    try:
        yield
    except Exception as e:
        context_info = f" в контексте '{context_name}'" if context_name else ""
        logger.error(f"Перехвачено исключение{context_info}")
        log_error(e, stack_level=2)
        raise  # Повторно вызываем исключение после логирования
