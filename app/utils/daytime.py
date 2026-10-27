"""
Время пользователя: часовой пояс и граница «сегодня».

Telegram не передаёт часовой пояс, поэтому он хранится в профиле
(users.utc_offset_min). В базе все даты — UTC без tzinfo.

День начинается за DAY_START_BEFORE_WAKE часов до утра пользователя:
если утро в 7:00, всё съеденное до 4:00 ночи относится ко вчерашнему дню.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

DEFAULT_OFFSET_MIN = 180  # Москва — пока пользователь не выбрал пояс
DEFAULT_WAKE_HOUR = 7
DAY_START_BEFORE_WAKE = 3

# (подпись, смещение в минутах) для кнопок выбора пояса
TIMEZONES = [
    ("Калининград", 120),
    ("Москва, СПб", 180),
    ("Самара", 240),
    ("Екатеринбург", 300),
    ("Омск", 360),
    ("Новосибирск, Красноярск", 420),
    ("Иркутск", 480),
    ("Якутск", 540),
    ("Владивосток", 600),
    ("Магадан", 660),
    ("Камчатка", 720),
]

WAKE_HOURS = [5, 6, 7, 8, 9, 10, 11, 12]


def utc_now() -> datetime:
    """Текущее время UTC без tzinfo — в таком виде даты лежат в базе"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def user_offset(user) -> int:
    offset = getattr(user, 'utc_offset_min', None)
    return DEFAULT_OFFSET_MIN if offset is None else offset


def day_start_hour(user) -> int:
    wake = getattr(user, 'wake_hour', None)
    wake = DEFAULT_WAKE_HOUR if wake is None else wake
    return max(0, wake - DAY_START_BEFORE_WAKE)


def to_local(dt_utc: datetime, user) -> datetime:
    return dt_utc + timedelta(minutes=user_offset(user))


def local_now(user) -> datetime:
    return to_local(utc_now(), user)


def day_bounds(user, days_ago: int = 0) -> Tuple[datetime, datetime]:
    """Границы «дня пользователя» в UTC: [начало, конец)"""
    offset = timedelta(minutes=user_offset(user))
    start_hour = day_start_hour(user)
    now_local = utc_now() + offset
    start_local = now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if now_local < start_local:
        start_local -= timedelta(days=1)
    start_local -= timedelta(days=days_ago)
    start_utc = start_local - offset
    return start_utc, start_utc + timedelta(days=1)


def day_label(user, days_ago: int = 0) -> str:
    """Подпись дня: «Сегодня, 27 октября»"""
    months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
              'августа', 'сентября', 'октября', 'ноября', 'декабря']
    start_utc, _ = day_bounds(user, days_ago)
    local = to_local(start_utc, user)
    date_text = f"{local.day} {months[local.month - 1]}"
    if days_ago == 0:
        return f"Сегодня, {date_text}"
    if days_ago == 1:
        return f"Вчера, {date_text}"
    return date_text


def format_offset(offset_min: int) -> str:
    sign = '+' if offset_min >= 0 else '−'
    hours, minutes = divmod(abs(offset_min), 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def parse_offset_input(text: str) -> Optional[int]:
    """
    Пояс из текста пользователя: текущее время («14:35») или смещение («+3», «UTC+5:30»).
    Возвращает смещение в минутах или None.
    """
    text = text.strip().upper().replace('UTC', '').replace('GMT', '').replace('−', '-')

    m = re.fullmatch(r'([+-])\s*(\d{1,2})(?::?(\d{2}))?', text)
    if m:
        sign = 1 if m.group(1) == '+' else -1
        minutes = int(m.group(2)) * 60 + int(m.group(3) or 0)
        offset = sign * minutes
        return offset if -12 * 60 <= offset <= 14 * 60 else None

    m = re.fullmatch(r'(\d{1,2})[:.\s](\d{2})', text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            return None
        now = utc_now()
        diff = (hour * 60 + minute) - (now.hour * 60 + now.minute)
        # Разница во времени — в пределах суток, приводим к диапазону [-12ч; +14ч]
        if diff < -12 * 60:
            diff += 24 * 60
        elif diff > 14 * 60:
            diff -= 24 * 60
        return int(round(diff / 15.0)) * 15

    return None
