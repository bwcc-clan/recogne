import asyncio
import logging
import os
import re
from configparser import ConfigParser, ExtendedInterpolation, MissingSectionHeaderError
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Optional

from cachetools import TTLCache
from cachetools.keys import hashkey


def to_timedelta(value):
    if not value:
        return timedelta(0)
    elif isinstance(value, int):
        return timedelta(seconds=value)
    elif isinstance(value, datetime):
        return value - datetime.now(tz=timezone.utc)
    elif isinstance(value, timedelta):
        return value
    else:
        raise ValueError('value needs to be datetime, timedelta or None')

def int_to_emoji(value: int):
    match value:
        case 0:
            return "0️⃣"
        case 1:
            return "1️⃣"
        case 2:
            return "2️⃣"
        case 3:
            return "3️⃣"
        case 4:
            return "4️⃣"
        case 5:
            return "5️⃣"
        case 6:
            return "6️⃣"
        case 7:
            return "7️⃣"
        case 8:
            return "8️⃣"
        case 9:
            return "9️⃣"
        case 10:
            return "🔟"
        case _:
            return f"**#{str(value)}**"

def get_name(user):
    return user.nick if user.nick else user.name

def add_empty_fields(embed):
    try:
        fields = len(embed._fields)
    except AttributeError:
        fields = 0
    if fields > 3:
        empty_fields_to_add = 3 - (fields % 3)
        if empty_fields_to_add in (1, 2):
            for _ in range(empty_fields_to_add):
                embed.add_field(name="‏", value="‏") # These are special characters that can not be seen
    return embed


def ttl_cache(size: int, seconds: int):
    def decorator(func):
        func.cache = TTLCache(size, ttl=seconds)
        @wraps(func)
        async def wrapper(*args, **kwargs):
            k = hashkey(*args, **kwargs)
            try:
                return func.cache[k]
            except KeyError:
                pass  # key not found
            v = await func(*args, **kwargs)
            try:
                func.cache[k] = v
            except ValueError:
                pass  # value too large
            return v
        return wrapper
    return decorator

class SingletonMeta(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class EnvInterpolation(ExtendedInterpolation):
    """
    Interpolation which expands environment variables in values. Usage:

    ```
    [mysection]
    Value=${ENV_VAR}
    ```
    """

    def before_read(self, parser, section, option, value):
        value = super().before_read(parser, section, option, value)
        return os.path.expandvars(value)


CONFIG = {}
def get_config() -> ConfigParser:
    global CONFIG
    if not CONFIG:
        parser = ConfigParser(interpolation=EnvInterpolation())
        try:
            parser.read('config.ini', encoding='utf-8')
        except MissingSectionHeaderError:
            # Most likely a BOM was added. This can happen automatically when
            # saving the file with Notepad. Let's open with UTF-8-BOM instead.
            parser.read('config.ini', encoding='utf-8-sig')
        CONFIG = parser
    return CONFIG


_SCHEDULER_TIME_BETWEEN_INTERVAL = timedelta(minutes=3)
def schedule_coro(dt: datetime, coro_func, *args, error_logger: Optional[logging.Logger] = None) -> asyncio.Task:
    """Schedule a coroutine for execution at a specific time.

    Time drift will be accounted for.

    Parameters
    ----------
    dt : datetime
        The date and time
    coro : Coroutine
        The coroutine to schedule
    """
    async def scheduled_coro():
        time_to_sleep = _SCHEDULER_TIME_BETWEEN_INTERVAL.total_seconds()

        time_left = dt - datetime.now(tz=timezone.utc)
        if not (time_left < timedelta(0)):

            while time_left > _SCHEDULER_TIME_BETWEEN_INTERVAL:
                await asyncio.sleep(time_to_sleep)
                time_left = dt - datetime.now(tz=timezone.utc)

            await asyncio.sleep(time_left.total_seconds())

        try:
            res = await coro_func(*args)
        except Exception:
            if error_logger:
                error_logger.exception('Scheduled coroutine raised an exception')
            else:
                raise

        return res

    return asyncio.create_task(scheduled_coro())


LOGS_FOLDER = Path('logs')
if not LOGS_FOLDER.exists():
    LOGS_FOLDER.mkdir()

def _get_logs_formatter(name: str = None, as_str: bool = False):
    if name:
        fmt = '[%(asctime)s][{}][%(levelname)s][%(module)s.%(funcName)s:%(lineno)s] %(message)s'.format(name)
    else:
        fmt = '[%(asctime)s][%(levelname)s][%(module)s.%(funcName)s:%(lineno)s] %(message)s'
    if as_str:
        return fmt
    else:
        return logging.Formatter(fmt)
def _assert_filename(text: str):
    return re.sub(r"[^\w\(\)_\-,\. ]", "_", text.replace(' ', '_'))

logging.basicConfig(
    level=logging.INFO,
    format=_get_logs_formatter(name='other', as_str=True),
)

def get_logger(session):
    logger = logging.getLogger(str(session.id))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        name = f"sess{session.id}_{_assert_filename(session.name)}.log"

        handler = logging.FileHandler(filename=LOGS_FOLDER / name, encoding='utf-8')
        handler.setFormatter(_get_logs_formatter())
        logger.addHandler(handler)

        handler = logging.StreamHandler()
        handler.setFormatter(_get_logs_formatter(f'sess{session.id}'))
        logger.addHandler(handler)
    return logger

def get_autosession_logger(autosession):
    logger = logging.getLogger(f"auto_{autosession.id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        name = f"auto{autosession.id}_{_assert_filename(autosession.credentials.name)}.log"

        handler = logging.FileHandler(filename=LOGS_FOLDER / name, encoding='utf-8')
        handler.setFormatter(_get_logs_formatter())
        logger.addHandler(handler)

        handler = logging.StreamHandler()
        handler.setFormatter(_get_logs_formatter(f'auto{autosession.id}'))
        handler.setLevel(logging.WARN)
        logger.addHandler(handler)
    return logger



def toTable(rows, spacing=2, title=None, just=None, rotate=False, rstrip=True):
    rowlen = len(rows[0])
    for row in rows:
        if len(row) != rowlen:
            raise ValueError('Not all rows are of equal length')

    if rotate:
        cols = rows
        rows = list(zip(*rows))
    else:
        cols = list(zip(*rows))

    if not just:
        just = 'l' * len(cols)
    elif len(just) != len(cols):
        raise ValueError('Justify setting is of incorrect length')

    sizes = [max([len(str(value)) for value in col]) for col in cols]

    output = list()
    space = " " * spacing
    justs = {
        'l': lambda i, val: str(val).ljust(sizes[i]),
        'c': lambda i, val: str(val).center(sizes[i]),
        'r': lambda i, val: str(val).rjust(sizes[i]),
    }
    for row in rows:
        line = space.join([justs[just[i]](i, value) for i, value in enumerate(row)])
        if rstrip:
            line = line.rstrip()
        output.append(line)

    if title:
        maxsize = max([len(line) for line in output])
        title = (" " + str(title) + " ").center(maxsize, "#")
        output.insert(0, title)

    return "\n".join(output)


def side_by_side(text1, *others, spacing=5):
    others = list(others)
    while others:
        text2 = others.pop(0)
        lines1 = text1.split('\n')
        lines2 = text2.split('\n')
        ljust = max([len(line) for line in lines1]) + spacing
        output = list()
        while lines1 or lines2:
            line1 = lines1.pop(0) if lines1 else ''
            if lines2:
                line2 = lines2.pop(0)
                output.append(line1.ljust(ljust) + line2)
            else:
                output.append(line1)
        text1 = "\n".join(output)
    return text1
