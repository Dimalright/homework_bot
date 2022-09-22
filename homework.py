import logging
import os
import sys
import time
import exception
import telegram
import requests
import json

from http import HTTPStatus

from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from endpoint import ENDPOINT

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(funcName)s - [%(levelname)s] - %(message)s'
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
handler = RotatingFileHandler('main.log',
                              maxBytes=50000000,
                              backupCount=5,
                              encoding='UTF-8'
                              )
logger.addHandler(handler)

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

TELEGRAM_RETRY_TIME = 600

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

ENDPOINT
VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message) -> None:
    """
    Отправляет сообщение в Телеграмм.
    В случае неудачи, вызывает ошибку. Логирует события.
    """
    failed_message = 'Не удалось отправить сообщение'
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Бот отправил сообщение {message}')
    except telegram.error.TelegramError:
        logger.error(failed_message)
        raise telegram.error.TelegramError(failed_message)


def get_api_answer(current_timestamp: int) -> dict:
    """
    Делает запрос к API Практикум.
    Возвращает ответ API преобразованный в тип данных Python.
    Принимает в качестве параметра временную метку.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        logger.info(f'Отправлен запрос к API Практикума. '
                    f'Код ответа API: {response.status_code}')
        if response.status_code != HTTPStatus.OK:
            raise response.raise_for_status()

    except requests.exceptions.RequestException as error:
        message = f'Эндпойнт недоступен: {error}'
        logger.error(message)
        raise requests.exceptions.RequestException(message)
    except json.decoder.JSONDecodeError as error:
        raise Exception((f'Ответ {response.text} получен не в виде JSON: '
                         f'{error}'))
    return response.json()


def check_response(response: dict) -> list:
    """
    Проверка корректности ответа API.
    В качестве параметра получает ответ
    API приведенный к типам данных Python (dict). Функция возвращает список
    домашних работ по ключу 'homeworks'.
    """
    logging.info('Начинаем проверку корректности ответа API.')
    if isinstance(response, dict):
        try:
            homework = response['homeworks']
        except KeyError as error:
            message = f'В ответе не обнаружен ключ {error}'
            logger.error(message)
            raise exception.KeyNotFound(message)
        if not isinstance(homework, list):
            raise TypeError('Ответ не содержит список домашних работ')
        message = 'Получены сведения о последней домашней работе'
        logger.info(message) if len(homework) else None
        return homework
    else:
        raise TypeError('В ответе API не обнаружен словарь')


def parse_status(homework):
    """Полученный ответ разделяем на имя и статус."""
    """И передаем его в сообщение."""
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status in VERDICTS.keys():
        verdict = VERDICTS.get(homework_status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """
    Проверяет доступность переменных окружения.
    Проверка токенов Практикума и
    Bot API, id чата получателя. Возвращает булево значение.
    """
    checker = True
    checker = all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))
    if not checker:
        logging.critical('Отсутствует переменная токена!!!')
    return checker


def main() -> None:
    """Основная логика работы бота."""
    logger.info('Бот запущен')

    if not check_tokens():
        message = 'Отсутствует одна из переменных окружения'
        logger.critical(message + '\nПрограмма остановлена.')
        raise exception.MissingVariable(message)

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except telegram.error.InvalidToken as error:
        message = f'Ошибка при создании бота: {error}'
        logger.critical(message + '\nПрограмма остановлена.')
        raise telegram.error.InvalidToken

    current_timestamp = int(time.time())
    last_homework = None
    last_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp - TELEGRAM_RETRY_TIME)
            homework = check_response(response)
            if homework and homework != last_homework:
                message = parse_status(homework[0])
                send_message(bot, message)
                last_homework = homework
            else:
                logger.debug('Статус домашней работы не изменился')
            current_timestamp = response.get('current_date')

        except Exception as error:
            if str(error) != last_error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                last_error = str(error)
        finally:
            time.sleep(TELEGRAM_RETRY_TIME)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
