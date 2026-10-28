"""
Данные с часов (Apple Health через команду iPhone): разбор, проверка, сохранение, отчёт.

Формат запроса (POST /health/v1/sync, заголовок X-FitBud-Key):
JSON-объект с плоскими ключами, значения — текст, по строке на образец данных
(«Команды» превращают список в текст через перевод строки):

  <metric>_d   — даты начала, ISO 8601 с часовым поясом
  <metric>_v   — значения (порядок совпадает с _d)
  <metric>_w_d / _w_v и <metric>_p_d / _p_v — то же по часам суток отдельно с часов и с iPhone
                 (шаги, дистанция, калории): сервер убирает задвоение, как «Здоровье»
  sleep_d, sleep_e, sleep_v                — начало, конец и фаза сна
  workout_d, workout_e, workout_t          — начало, конец, вид тренировки
  workout_kcal, workout_km, workout_hr, workout_hrmax  — необязательные

Команда отправляет данные за последние 2 дня: повторы перезаписывают день целиком,
поэтому пропущенный запуск восполняется следующим.
"""
import hashlib
import math
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, delete

from database.database import async_session, HealthDaily, HealthDevice, WorkoutEntry, User
from utils.daytime import day_bounds, to_local, utc_now
from utils import nutrition

MAX_LINES = 500
MAX_BODY_BYTES = 256 * 1024

# metric: (как сводить несколько значений за день, допустимый диапазон)
DAILY_METRICS = {
    'steps': ('sum', 0, 150_000),
    'distance': ('sum', 0, 300),  # км ходьбы и бега
    'flights': ('sum', 0, 500),
    'active_kcal': ('sum', 0, 10_000),
    'resting_kcal': ('sum', 0, 6_000),
    'exercise_min': ('sum', 0, 1_440),
    'stand_hours': ('sum', 0, 24),
    'resting_hr': ('avg', 25, 200),
    'hr_avg': ('avg', 25, 230),
    'hr_max': ('max', 25, 250),
    'walking_hr': ('avg', 25, 230),
    'hrv': ('avg', 1, 300),  # мс
    'spo2': ('avg', 50, 100),  # %
    'resp_rate': ('avg', 4, 60),
    'wrist_temp': ('avg', -5, 5),  # отклонение от обычной, °C
    'weight': ('last', 25, 350),
    'body_fat': ('last', 2, 70),  # %
    'vo2max': ('last', 10, 95),
}
SLEEP_METRICS = ('sleep_min', 'sleep_core_min', 'sleep_deep_min', 'sleep_rem_min', 'sleep_awake_min')

# Фаза сна: русские и английские названия из «Команд» и числовые коды HealthKit
SLEEP_STAGES = [
    ('inbed', ('в кровати', 'в постели', 'in bed', 'inbed', '0')),
    ('awake', ('бодрств', 'пробужд', 'awake', '2')),
    ('core', ('базов', 'основн', 'лёгк', 'легк', 'core', '3')),
    ('deep', ('глубок', 'deep', '4')),
    ('rem', ('быстр', 'rem', '5')),
    ('asleep', ('сон', 'спит', 'asleep', 'unspecified', '1')),
]

# Вид тренировки → категория, по ней ищем дубли с записанным текстом
WORKOUT_CATEGORIES = [
    ('run', ('бег', 'пробеж', 'running', 'run', 'jog')),
    ('walk', ('ходьб', 'прогул', 'поход', 'walk', 'hik')),
    ('cycle', ('вело', 'сайкл', 'cycl', 'bike')),
    ('swim', ('плав', 'бассейн', 'swim')),
    ('yoga', ('йог', 'пилатес', 'растяж', 'стретч', 'yoga', 'pilates', 'stretch')),
    ('dance', ('танц', 'зумб', 'dance')),
    ('strength', ('силов', 'зал', 'штанг', 'гантел', 'функцион', 'кроссфит', 'интервал', 'hiit',
                  'strength', 'functional', 'crossfit', 'core training')),
]
# MET по категории — если часы не прислали калории тренировки
CATEGORY_MET = {'run': 9.8, 'walk': 3.5, 'cycle': 7.5, 'swim': 7.0, 'yoga': 2.5,
                'dance': 6.0, 'strength': 5.0, 'other': 5.0}

DUPLICATE_WINDOW = timedelta(hours=3)
SLEEP_GAP = timedelta(hours=2)


# ==================== Ключи ====================

def hash_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


async def issue_token(user_id: int) -> str:
    """Новый ключ для команды; старые ключи пользователя отключаются"""
    token = secrets.token_urlsafe(24)
    now = utc_now()
    async with async_session() as session:
        devices = (await session.execute(
            select(HealthDevice).where(HealthDevice.user_id == user_id).where(HealthDevice.revoked_at.is_(None))
        )).scalars().all()
        for device in devices:
            device.revoked_at = now
        session.add(HealthDevice(user_id=user_id, token_hash=hash_token(token)))
        await session.commit()
    return token


async def revoke_tokens(user_id: int):
    async with async_session() as session:
        devices = (await session.execute(
            select(HealthDevice).where(HealthDevice.user_id == user_id).where(HealthDevice.revoked_at.is_(None))
        )).scalars().all()
        for device in devices:
            device.revoked_at = utc_now()
        await session.commit()


async def active_device(user_id: int) -> Optional[HealthDevice]:
    async with async_session() as session:
        return (await session.execute(
            select(HealthDevice).where(HealthDevice.user_id == user_id).where(HealthDevice.revoked_at.is_(None))
            .order_by(HealthDevice.id.desc())
        )).scalars().first()


async def device_by_token(token: str) -> Optional[HealthDevice]:
    if not token:
        return None
    async with async_session() as session:
        return (await session.execute(
            select(HealthDevice).where(HealthDevice.token_hash == hash_token(token))
            .where(HealthDevice.revoked_at.is_(None))
        )).scalar_one_or_none()


# ==================== Разбор ====================

def _lines(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(v) for v in value]
    else:
        items = str(value).replace('\r', '').split('\n')
    return [item.strip() for item in items if item.strip()][:MAX_LINES]


def _number(text: str) -> Optional[float]:
    cleaned = text.replace(' ', '').replace(' ', '').replace(' ', '').replace(',', '.')
    match = re.search(r'-?\d+(?:\.\d+)?', cleaned)
    if not match:
        return None
    number = float(match.group())
    return number if math.isfinite(number) else None


def _datetime(text: str) -> Optional[datetime]:
    """ISO 8601 → aware datetime (дата без времени — полночь UTC)"""
    try:
        parsed = datetime.fromisoformat(text.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _merge_sources(payload: Dict, metric: str) -> Optional[Dict[date, float]]:
    """
    Шаги, дистанция, калории — с часов (<metric>_w_*) и с iPhone (<metric>_p_*) по часам суток.
    Как в «Здоровье»: если в один и тот же час считали оба устройства, берём большее, а не сумму.
    None — если таких данных в запросе нет.
    """
    hours: Dict[datetime, Tuple[date, Dict[str, float]]] = {}
    for source in ('w', 'p'):
        dates = _lines(payload.get(f'{metric}_{source}_d'))
        values = _lines(payload.get(f'{metric}_{source}_v'))
        for date_text, value_text in zip(dates, values):
            moment, value = _datetime(date_text), _number(value_text)
            if moment is None or value is None or value < 0:
                continue
            hour = moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            day, by_source = hours.setdefault(hour, (moment.date(), {}))
            by_source[source] = by_source.get(source, 0) + value
    if not hours:
        return None
    days: Dict[date, float] = {}
    for day, by_source in hours.values():
        days[day] = days.get(day, 0) + max(by_source.values())
    return days


def parse_daily(payload: Dict) -> Dict[Tuple[date, str], float]:
    """{(день, показатель): значение} — день берётся из даты образца в поясе телефона"""
    result: Dict[Tuple[date, str], float] = {}
    for metric, (mode, low, high) in DAILY_METRICS.items():
        merged = _merge_sources(payload, metric) if mode == 'sum' else None
        if merged is not None:
            for day, value in merged.items():
                if low <= value <= high:
                    result[(day, metric)] = round(value, 2)
            continue
        dates = _lines(payload.get(f'{metric}_d'))
        values = _lines(payload.get(f'{metric}_v'))
        grouped: Dict[date, List[float]] = {}
        for date_text, value_text in zip(dates, values):
            moment, value = _datetime(date_text), _number(value_text)
            if moment is None or value is None:
                continue
            if metric in ('spo2', 'body_fat') and 0 < value <= 1:
                value *= 100  # «Команды» иногда отдают доли, а не проценты
            grouped.setdefault(moment.date(), []).append(value)
        for day, values_of_day in grouped.items():
            if mode == 'sum':
                value = sum(values_of_day)
            elif mode == 'avg':
                value = sum(values_of_day) / len(values_of_day)
            elif mode == 'max':
                value = max(values_of_day)
            else:
                value = values_of_day[-1]
            if low <= value <= high:
                result[(day, metric)] = round(value, 2)
    return result


def _sleep_stage(text: str) -> Optional[str]:
    low = text.strip().lower()
    for stage, keys in SLEEP_STAGES:
        if any(low == key or (not key.isdigit() and key in low) for key in keys):
            return stage
    return None


def parse_sleep(payload: Dict) -> Dict[date, Dict]:
    """Сон по ночам: ночь относится ко дню, когда человек проснулся"""
    starts, ends, stages = (_lines(payload.get(k)) for k in ('sleep_d', 'sleep_e', 'sleep_v'))
    segments = []
    for start_text, end_text, stage_text in zip(starts, ends, stages):
        start, end, stage = _datetime(start_text), _datetime(end_text), _sleep_stage(stage_text)
        if not start or not end or not stage or end <= start or end - start > timedelta(hours=16):
            continue
        segments.append((start, end, stage))

    # Склеиваем отрезки в ночи (перерыв меньше 2 часов — та же ночь),
    # ночь относится ко дню, когда человек проснулся — даже если легла до полуночи
    segments.sort(key=lambda seg: seg[0])
    sessions: List[List] = []
    for segment in segments:
        if sessions and segment[0] <= max(e for _, e, _ in sessions[-1]) + SLEEP_GAP:
            sessions[-1].append(segment)
        else:
            sessions.append([segment])
    nights: Dict[date, List] = {}
    for session in sessions:
        wake_day = max(e for _, e, _ in session).date()
        nights.setdefault(wake_day, []).extend(session)

    result = {}
    for day, parts in nights.items():
        has_stages = any(stage in ('core', 'deep', 'rem') for _, _, stage in parts)
        minutes = {'core': 0.0, 'deep': 0.0, 'rem': 0.0, 'asleep': 0.0, 'awake': 0.0}
        asleep_parts = []
        awakenings = 0
        for start, end, stage in parts:
            length = (end - start).total_seconds() / 60
            if stage == 'inbed' or (stage == 'asleep' and has_stages):
                continue  # «в кровати» — не сон; общий «сон» дублирует фазы с часов
            minutes[stage] += length
            if stage == 'awake':
                awakenings += 1
            else:
                asleep_parts.append((start, end))
        total = minutes['core'] + minutes['deep'] + minutes['rem'] + minutes['asleep']
        if total < 30 or total > 20 * 60:
            continue
        result[day] = {
            'sleep_min': round(total),
            'sleep_core_min': round(minutes['core'] + minutes['asleep']),
            'sleep_deep_min': round(minutes['deep']),
            'sleep_rem_min': round(minutes['rem']),
            'sleep_awake_min': round(minutes['awake']),
            'extra': {
                'bed': min(s for s, _ in asleep_parts).isoformat(),
                'wake': max(e for _, e in asleep_parts).isoformat(),
                'awakenings': awakenings,
                'stages': has_stages,
            },
        }
    return result


def workout_category(name: str) -> str:
    low = (name or '').lower()
    for category, keys in WORKOUT_CATEGORIES:
        if any(key in low for key in keys):
            return category
    return 'other'


def _clean_name(text: str) -> str:
    text = ''.join(ch for ch in text if ch.isprintable()).replace('<', '').replace('>', '').strip()
    return text[:60] or 'Тренировка'


def parse_workouts(payload: Dict) -> List[Dict]:
    starts, ends, names = (_lines(payload.get(k)) for k in ('workout_d', 'workout_e', 'workout_t'))
    optional = {k: _lines(payload.get(f'workout_{k}')) for k in ('kcal', 'km', 'hr', 'hrmax')}
    workouts = []
    for index, (start_text, end_text, name) in enumerate(zip(starts, ends, names)):
        start, end = _datetime(start_text), _datetime(end_text)
        if not start or not end or end <= start:
            continue
        duration = (end - start).total_seconds() / 60
        if not 1 <= duration <= 600:
            continue

        def opt(key, low, high):
            values = optional[key]
            value = _number(values[index]) if index < len(values) else None
            return value if value is not None and low <= value <= high else None

        workouts.append({
            'name': _clean_name(name),
            'start': start,
            'end': end,
            'duration': int(round(duration)),
            'kcal': opt('kcal', 1, 5000),
            'km': opt('km', 0.01, 300),
            'hr': opt('hr', 30, 230),
            'hrmax': opt('hrmax', 30, 250),
            'external_id': hashlib.sha1(f"{_to_utc_naive(start).isoformat()}|{name.strip().lower()}".encode()).hexdigest()[:32],
        })
    return workouts


# ==================== Сохранение ====================

async def store_payload(user: User, payload: Dict) -> Dict:
    """Сохранить данные. Возвращает сводку: дни, показатели, новые тренировки"""
    daily = parse_daily(payload)
    sleep = parse_sleep(payload)
    workouts = parse_workouts(payload)

    rows: Dict[Tuple[date, str], Tuple[float, Optional[Dict]]] = {key: (value, None) for key, value in daily.items()}
    for day, night in sleep.items():
        for metric in SLEEP_METRICS:
            rows[(day, metric)] = (night[metric], night['extra'] if metric == 'sleep_min' else None)

    new_workouts = []
    async with async_session() as session:
        for (day, metric), (value, extra) in rows.items():
            existing = (await session.execute(
                select(HealthDaily).where(HealthDaily.user_id == user.telegram_id)
                .where(HealthDaily.day == day).where(HealthDaily.metric == metric)
            )).scalar_one_or_none()
            if existing:
                existing.value, existing.extra = value, extra
            else:
                session.add(HealthDaily(user_id=user.telegram_id, day=day, metric=metric, value=value, extra=extra))

        for workout in workouts:
            exists = (await session.execute(
                select(WorkoutEntry.id).where(WorkoutEntry.user_id == user.telegram_id)
                .where(WorkoutEntry.external_id == workout['external_id'])
            )).first()
            if exists:
                continue
            category = workout_category(workout['name'])
            kcal = workout['kcal'] or nutrition.workout_calories(
                CATEGORY_MET[category], user.weight or 70, workout['duration'])
            entry = WorkoutEntry(
                user_id=user.telegram_id,
                workout_type=workout['name'],
                duration=workout['duration'],
                calories_burned=int(round(kcal)),
                distance=workout['km'],
                avg_hr=workout['hr'],
                max_hr=workout['hrmax'],
                source_type='watch',
                external_id=workout['external_id'],
                started_at=_to_utc_naive(workout['start']),
                ended_at=_to_utc_naive(workout['end']),
                created_at=_to_utc_naive(workout['end']),
            )
            session.add(entry)
            await session.flush()
            new_workouts.append(entry)
        await session.commit()

    return {
        'days': sorted({day for day, _ in rows}),
        'metrics': len(rows),
        'new_workouts': new_workouts,
    }


# ==================== Дубли тренировок ====================

def _similar_duration(a: int, b: int) -> bool:
    return abs(a - b) <= max(a, b) / 3


async def find_duplicate(workout: WorkoutEntry) -> Optional[WorkoutEntry]:
    """
    Похожая тренировка из другого источника (часы ↔ записанная текстом):
    тот же вид, текстовая запись сделана во время тренировки с часов или до 3 часов после неё,
    длительность отличается не больше чем на треть.
    """
    is_watch = workout.source_type == 'watch'
    async with async_session() as session:
        query = (
            select(WorkoutEntry)
            .where(WorkoutEntry.user_id == workout.user_id)
            .where(WorkoutEntry.id != workout.id)
            .where(WorkoutEntry.deleted_at.is_(None))
        )
        if is_watch:
            query = (query.where(WorkoutEntry.source_type != 'watch')
                     .where(WorkoutEntry.created_at >= workout.started_at)
                     .where(WorkoutEntry.created_at <= workout.ended_at + DUPLICATE_WINDOW))
        else:
            query = (query.where(WorkoutEntry.source_type == 'watch')
                     .where(WorkoutEntry.started_at <= workout.created_at)
                     .where(WorkoutEntry.ended_at >= workout.created_at - DUPLICATE_WINDOW))
        candidates = (await session.execute(query)).scalars().all()

    category = workout_category(workout.workout_type)
    for candidate in candidates:
        if workout_category(candidate.workout_type) != category:
            continue
        if category == 'other' and candidate.workout_type.lower() != workout.workout_type.lower():
            continue
        if _similar_duration(candidate.duration or 0, workout.duration or 0):
            return candidate
    return None


# ==================== Показатели дня ====================

def health_day(user, days_ago: int = 0) -> date:
    """Календарная дата «дня пользователя» — по ней ищем показатели с часов"""
    start, _ = day_bounds(user, days_ago)
    return to_local(start, user).date()


async def day_metrics(user, days_ago: int = 0) -> Dict[str, HealthDaily]:
    day = health_day(user, days_ago)
    async with async_session() as session:
        rows = (await session.execute(
            select(HealthDaily).where(HealthDaily.user_id == user.telegram_id).where(HealthDaily.day == day)
        )).scalars().all()
    return {row.metric: row for row in rows}


async def baseline(user, metric: str, days_ago: int = 0, days: int = 7) -> Optional[float]:
    """Среднее значение показателя за предыдущие дни — для сравнения «с собой»"""
    day = health_day(user, days_ago)
    async with async_session() as session:
        values = (await session.execute(
            select(HealthDaily.value).where(HealthDaily.user_id == user.telegram_id)
            .where(HealthDaily.metric == metric)
            .where(HealthDaily.day < day).where(HealthDaily.day >= day - timedelta(days=days))
        )).scalars().all()
    return sum(values) / len(values) if len(values) >= 3 else None


# ==================== Отчёт ====================

STEPS_GOAL = 10_000
EXERCISE_GOAL = 30
STAND_GOAL = 12


def _bar(value: float, target: float, width: int = 10) -> str:
    return nutrition.progress_bar(value, target, width)


def _hm(minutes: float) -> str:
    minutes = int(round(minutes))
    return f"{minutes // 60} ч {minutes % 60:02d} мин"


def _local_time(iso: str, user) -> str:
    moment = _datetime(iso)
    return to_local(_to_utc_naive(moment), user).strftime('%H:%M') if moment else '?'


def _trend(value: float, usual: Optional[float], lower_is_better: bool, threshold: float) -> str:
    if usual is None:
        return ""
    diff = value - usual
    if abs(diff) < threshold:
        return f" (обычно {usual:.0f}) — как обычно"
    better = diff < 0 if lower_is_better else diff > 0
    arrow = '⬇️' if diff < 0 else '⬆️'
    return f" (обычно {usual:.0f}) {arrow} " + ("хорошо" if better else "стоит отдохнуть")


async def watch_report(user, days_ago: int, workouts: List[WorkoutEntry], title: str) -> Optional[str]:
    """Блок «⌚ С часов» за день; None — если данных за день нет"""
    m = await day_metrics(user, days_ago)
    watch_workouts = [w for w in workouts if w.source_type == 'watch']
    if not m and not watch_workouts:
        return None

    def v(key):
        return m[key].value if key in m else None

    lines = [f"⌚ <b>С часов — {escape(title)}</b>"]

    move = []
    if v('steps') is not None:
        move.append(f"Шаги: <b>{int(v('steps')):,}</b> / {STEPS_GOAL:,}  {_bar(v('steps'), STEPS_GOAL)}".replace(',', ' '))
    extra = []
    if v('distance') is not None:
        extra.append(f"дистанция {nutrition.fmt(round(v('distance'), 1))} км")
    if v('flights') is not None:
        extra.append(f"этажей {int(v('flights'))}")
    if extra:
        move.append(", ".join(extra).capitalize())
    rings = []
    if v('exercise_min') is not None:
        rings.append(f"упражнения {int(v('exercise_min'))}/{EXERCISE_GOAL} мин" + (" ✅" if v('exercise_min') >= EXERCISE_GOAL else ""))
    if v('stand_hours') is not None:
        rings.append(f"разминка {int(v('stand_hours'))}/{STAND_GOAL} ч" + (" ✅" if v('stand_hours') >= STAND_GOAL else ""))
    if rings:
        move.append("⭕ " + " · ".join(rings).capitalize())
    if move:
        lines += ["", "👟 <b>Движение</b>"] + move

    energy = []
    if v('active_kcal') is not None:
        energy.append(f"активные <b>{int(v('active_kcal'))}</b> ккал")
    if v('resting_kcal') is not None:
        energy.append(f"в покое {int(v('resting_kcal'))} ккал")
    if energy:
        lines += ["", "🔥 <b>Энергия</b>", " · ".join(energy).capitalize()]

    if watch_workouts:
        lines += ["", "🏃 <b>Тренировки</b>"]
        for w in watch_workouts:
            parts = [escape(w.workout_type)]
            if w.started_at and w.ended_at:
                parts.append(f"{to_local(w.started_at, user):%H:%M}–{to_local(w.ended_at, user):%H:%M}")
            parts.append(f"{w.duration} мин")
            if w.distance:
                parts.append(f"{nutrition.fmt(round(w.distance, 1))} км")
            parts.append(f"{w.calories_burned} ккал")
            if w.avg_hr:
                parts.append(f"пульс {int(w.avg_hr)}" + (f" (макс {int(w.max_hr)})" if w.max_hr else ""))
            lines.append(" · ".join(parts))

    heart = []
    if v('resting_hr') is not None:
        usual = await baseline(user, 'resting_hr', days_ago)
        heart.append(f"Пульс покоя: <b>{int(v('resting_hr'))}</b>" + _trend(v('resting_hr'), usual, True, 3))
    if v('hrv') is not None:
        usual = await baseline(user, 'hrv', days_ago)
        heart.append(f"ВСР: <b>{int(v('hrv'))}</b> мс" + _trend(v('hrv'), usual, False, 5))
    if v('hr_avg') is not None:
        heart.append(f"Средний пульс: {int(v('hr_avg'))}" + (f" · максимум {int(v('hr_max'))}" if v('hr_max') else ""))
    if v('walking_hr') is not None:
        heart.append(f"Пульс при ходьбе: {int(v('walking_hr'))}")
    if heart:
        lines += ["", "❤️ <b>Сердце</b>"] + heart

    if v('sleep_min') is not None:
        info = m['sleep_min'].extra or {}
        sleep_min = v('sleep_min')
        mark = "✅" if 7 * 60 <= sleep_min <= 9 * 60 else ("⚠️ мало" if sleep_min < 7 * 60 else "много")
        header = "😴 <b>Сон</b>"
        if info.get('bed') and info.get('wake'):
            header += f" (с {_local_time(info['bed'], user)} до {_local_time(info['wake'], user)})"
        detail = f"<b>{_hm(sleep_min)}</b> {mark}"
        if info.get('stages'):
            for key, label in (('sleep_deep_min', 'глубокий'), ('sleep_rem_min', 'быстрый'),
                               ('sleep_core_min', 'базовый')):
                if v(key):
                    detail += f" · {label} {_hm(v(key))}"
        if info.get('awakenings'):
            detail += f" · пробуждений {info['awakenings']}"
        lines += ["", header, detail]

    recovery = []
    if v('spo2') is not None:
        recovery.append(f"кислород {int(round(v('spo2')))}%")
    if v('resp_rate') is not None:
        recovery.append(f"дыхание {nutrition.fmt(round(v('resp_rate'), 1))}/мин")
    if v('wrist_temp') is not None:
        temp = v('wrist_temp')
        recovery.append("температура в норме" if abs(temp) < 0.5 else f"температура {temp:+.1f} °C от обычной")
    if v('vo2max') is not None:
        recovery.append(f"VO₂max {nutrition.fmt(round(v('vo2max'), 1))}")
    if recovery:
        lines += ["", "🫁 " + " · ".join(recovery).capitalize()]

    body = []
    if v('weight') is not None:
        body.append(f"вес {nutrition.fmt(round(v('weight'), 1))} кг")
    if v('body_fat') is not None:
        body.append(f"жир {nutrition.fmt(round(v('body_fat'), 1))}%")
    if body:
        lines += ["", "⚖️ " + " · ".join(body).capitalize()]

    tips = await _watch_tips(user, days_ago, m, watch_workouts)
    if tips:
        lines.append("")
        lines += [f"💡 {tip}" for tip in tips]
    return "\n".join(lines)


async def _watch_tips(user, days_ago, m, watch_workouts) -> List[str]:
    """Советы по часам — фиксированные шаблоны"""
    tips = []
    sleep = m['sleep_min'].value if 'sleep_min' in m else None
    resting = m['resting_hr'].value if 'resting_hr' in m else None
    usual_resting = await baseline(user, 'resting_hr', days_ago) if resting is not None else None
    if resting is not None and usual_resting is not None and resting - usual_resting >= 5:
        tips.append("Пульс покоя заметно выше обычного — возможно, организму нужен отдых.")
    elif sleep is not None and sleep >= 7 * 60 and resting is not None and usual_resting is not None and resting <= usual_resting:
        tips.append("Хороший сон и спокойный пульс — подходящий день для интенсивной тренировки.")
    if sleep is not None and sleep < 6 * 60:
        tips.append("Сна меньше 6 часов — в такие дни сложнее удержаться от сладкого.")
    if watch_workouts:
        tips.append("Была тренировка — не забудь добрать белок.")
    return tips[:2]


def watch_energy(user, m: Dict[str, HealthDaily], workouts: List[WorkoutEntry]) -> Optional[Dict]:
    """
    Энергия дня по часам: база (обмен × 1,2 ± цель) + активные калории с часов.
    Тренировки, записанные текстом (не с часов), прибавляются сверху.
    None — если часы за этот день активные калории не прислали.
    """
    if 'active_kcal' not in m:
        return None
    watch_workouts = [w for w in workouts if w.source_type == 'watch']
    manual_workouts = [w for w in workouts if w.source_type != 'watch']
    active = int(round(m['active_kcal'].value))
    watch_workout_kcal = sum(w.calories_burned or 0 for w in watch_workouts)
    return {
        'base': nutrition.watch_base_calories(user),
        'active': active,
        'movement': max(0, active - watch_workout_kcal),
        'steps': int(m['steps'].value) if 'steps' in m else None,
        'watch_workouts': watch_workouts,
        'manual_workouts': manual_workouts,
        'manual_kcal': sum(w.calories_burned or 0 for w in manual_workouts),
    }
