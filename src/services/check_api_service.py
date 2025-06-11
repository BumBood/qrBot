import httpx
import os
from typing import Optional, Dict, Any, Union
from logger import logger


async def verify_check(
    token: str,
    fn: Optional[str] = None,
    fd: Optional[str] = None,
    fp: Optional[str] = None,
    time: Optional[str] = None,
    n: Optional[str] = None,
    s: Optional[str] = None,
    qr_raw: Optional[str] = None,
    qr_url: Optional[str] = None,
    qr_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Проверяет чек через API proverkacheka.com

    Поддерживает 4 формата запросов:
    1. По параметрам чека (fn, fd, fp, time, n, s)
    2. По сырым данным QR-кода (qr_raw)
    3. По URL изображения QR-кода (qr_url)
    4. По файлу изображения QR-кода (qr_file_path)

    Args:
        token: Токен доступа к API
        fn: Номер ФН (для формата 1)
        fd: Номер ФД (для формата 1)
        fp: Номер ФП (для формата 1)
        time: Время с чека в формате YYYYMMDDTHHMM (для формата 1)
        n: Вид кассового чека (для формата 1)
        s: Сумма чека (для формата 1)
        qr_raw: Сырые данные QR-кода (для формата 2)
        qr_url: URL изображения QR-кода (для формата 3)
        qr_file_path: Путь к файлу изображения QR-кода (для формата 4)

    Returns:
        dict: Результат проверки чека

    Raises:
        ValueError: Если не указаны необходимые параметры
        httpx.RequestError: При ошибке отправки запроса
    """
    url = "https://proverkacheka.com/api/v1/check/get"
    data = {"token": token, "qr": "0"}
    files = None
    file_obj = None

    try:
        # Формат 1: По параметрам чека
        if all([fn, fd, fp, time, n, s]):
            data.update({"fn": fn, "fd": fd, "fp": fp, "t": time, "n": n, "s": s})
        # Формат 2: По сырым данным QR-кода
        elif qr_raw:
            data["qrraw"] = qr_raw
        # Формат 3: По URL изображения QR-кода
        elif qr_url:
            data["qrurl"] = qr_url
        # Формат 4: По файлу изображения QR-кода
        elif qr_file_path:
            if not os.path.exists(qr_file_path):
                raise ValueError(f"Файл не найден: {qr_file_path}")
            file_obj = open(qr_file_path, "rb")
            files = {"qrfile": file_obj}
        else:
            raise ValueError("Не указаны необходимые параметры для проверки чека")

        logger.info(f"Отправка запроса в API proverkacheka.com: {data}")

        timeout = httpx.Timeout(30.0, connect=60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, data=data, files=files)

        if response.status_code != 200:
            logger.error(
                f"Ошибка API proverkacheka.com: {response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "error": f"Ошибка API: {response.status_code}",
                "details": response.text,
            }

        result = response.json()
        logger.info(f"Получен ответ от API proverkacheka.com: {result}")

        # Проверяем наличие ошибок в ответе
        if result.get("code") != 1:
            logger.error(f"Ошибка в ответе API proverkacheka.com: {result.get('data')}")
            return {
                "success": False,
                "error": "Ошибка проверки чека",
                "details": result.get("data", {}),
            }

        return {"success": True, "data": result.get("data", {})}

    except httpx.RequestError as e:
        logger.error(f"Ошибка при отправке запроса в API proverkacheka.com: {str(e)}")
        return {"success": False, "error": f"Ошибка при отправке запроса: {str(e)}"}

    except Exception as e:
        logger.error(
            f"Непредвиденная ошибка при работе с API proverkacheka.com: {str(e)}"
        )
        return {"success": False, "error": f"Непредвиденная ошибка: {str(e)}"}

    finally:
        # Закрываем файл, если он был открыт
        if file_obj:
            try:
                file_obj.close()
            except Exception as e:
                logger.error(f"Ошибка при закрытии файла: {str(e)}")
