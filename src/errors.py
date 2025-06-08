class BotError(Exception):
    """Базовый класс для всех ошибок бота"""

    pass


class ReceiptValidationError(BotError):
    """Ошибка валидации чека"""

    pass


class FNCApiError(BotError):
    """Ошибка при работе с API ФНС"""

    pass


class DatabaseError(BotError):
    """Ошибка при работе с базой данных"""

    pass


class QRCodeError(BotError):
    """Ошибка при распознавании QR-кода"""

    pass
