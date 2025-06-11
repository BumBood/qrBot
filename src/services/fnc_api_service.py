import httpx
from config import FNC_API_KEY, FNC_API_URL
from errors import FNCApiError
from logger import logger


async def verify_receipt(fn: str, fd: str, fpd: str, amount: float) -> dict:
    """
    Отправляет запрос к API ФНС для проверки чека

    Args:
        fn: Номер ФН
        fd: Номер ФД
        fpd: Номер ФПД
        amount: Сумма чека

    Returns:
        dict: Результат проверки

    Raises:
        FNCApiError: Если произошла ошибка при работе с API
    """
    try:
        params = {"fn": fn, "fd": fd, "fpd": fpd, "sum": amount, "token": FNC_API_KEY}

        logger.info(f"Отправка запроса в ФНС API: {params}")

        async with httpx.AsyncClient() as client:
            response = await client.get(FNC_API_URL, params=params)

        if response.status_code != 200:
            logger.error(f"Ошибка API ФНС: {response.status_code} - {response.text}")
            raise FNCApiError(f"Ошибка API ФНС: {response.status_code}")

        data = response.json()
        logger.info(f"Получен ответ от API ФНС: {data}")

        # Проверяем наличие ошибок в ответе
        if "error" in data:
            logger.error(f"Ошибка в ответе API ФНС: {data['error']}")
            raise FNCApiError(f"Ошибка в ответе API ФНС: {data['error']}")

        return data

    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса в API ФНС: {str(e)}")
        raise FNCApiError(f"Ошибка при отправке запроса в API ФНС: {str(e)}")

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при работе с API ФНС: {str(e)}")
        raise FNCApiError(f"Непредвиденная ошибка при работе с API ФНС: {str(e)}")
