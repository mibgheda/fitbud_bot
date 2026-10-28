"""
Дневник пользователя: сохранение, правка и удаление записей, отчёты за день.
"""
from datetime import timedelta
from html import escape
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from database.database import async_session, User, CalorieEntry, WorkoutEntry
from utils.daytime import day_bounds, day_label, to_local, utc_now
from utils import nutrition, health

UNDO_WINDOW = timedelta(minutes=2)


async def get_user(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


async def load_day(user: User, days_ago: int = 0) -> Tuple[List[CalorieEntry], List[WorkoutEntry]]:
    start, end = day_bounds(user, days_ago)
    async with async_session() as session:
        entries = (await session.execute(
            select(CalorieEntry)
            .where(CalorieEntry.user_id == user.telegram_id)
            .where(CalorieEntry.created_at >= start)
            .where(CalorieEntry.created_at < end)
            .where(CalorieEntry.deleted_at.is_(None))
            .order_by(CalorieEntry.created_at)
        )).scalars().all()
        workouts = (await session.execute(
            select(WorkoutEntry)
            .where(WorkoutEntry.user_id == user.telegram_id)
            .where(WorkoutEntry.created_at >= start)
            .where(WorkoutEntry.created_at < end)
            .where(WorkoutEntry.deleted_at.is_(None))
            .order_by(WorkoutEntry.created_at)
        )).scalars().all()
    return list(entries), list(workouts)


def _meal_name(items: List[Dict]) -> str:
    return ", ".join(item['name'] for item in items)[:255] or "Еда"


def _apply_items(entry: CalorieEntry, items: List[Dict], meal_type: str):
    totals = nutrition.meal_totals(items)
    entry.items = items
    entry.food_name = _meal_name(items)
    entry.calories = totals['calories']
    entry.protein = totals['protein']
    entry.fats = totals['fats']
    entry.carbs = totals['carbs']
    entry.fiber = totals['fiber']
    entry.sugar = totals['sugar']
    entry.water_ml = totals['water_ml']
    entry.drinks_ml = totals['drinks_ml']
    entry.soup_ml = totals['soup_ml']
    entry.alcohol = totals['alcohol'] or None
    water_only = nutrition.is_water_only(items)
    entry.meal_type = 'water' if water_only else (meal_type if meal_type != 'none' else 'snack')


def _apply_workout(entry: WorkoutEntry, workout: Dict, weight: float):
    entry.workout_type = workout['name'][:100]
    entry.duration = workout['duration_min']
    entry.met = workout['met']
    entry.distance = workout['distance_km'] or None
    entry.calories_burned = nutrition.workout_calories(workout['met'], weight, workout['duration_min'])


async def save_result(user: User, result: Dict, source_type: str, original_text: Optional[str],
                      confidence: Optional[float] = None) -> List[Tuple[str, int, str]]:
    """Сохранить разобранное сообщение. Возвращает [(kind, id, подпись)] — f: еда, w: тренировка"""
    saved = []
    async with async_session() as session:
        if result['items']:
            entry = CalorieEntry(
                user_id=user.telegram_id,
                source_type=source_type,
                source_data={'text': original_text} if original_text else None,
                ai_confidence=confidence,
            )
            _apply_items(entry, result['items'], result.get('meal_type', 'none'))
            session.add(entry)
            await session.flush()
            saved.append(('f', entry.id, 'еду'))
        for workout in result['workouts']:
            entry = WorkoutEntry(user_id=user.telegram_id, source_type=source_type, ai_confidence=confidence)
            _apply_workout(entry, workout, user.weight or 70)
            session.add(entry)
            await session.flush()
            saved.append(('w', entry.id, workout['name'][:20]))
        await session.commit()
    return saved


async def save_water(user: User, ml: int) -> int:
    items = [{
        'name': f"Вода, {ml} мл", 'calories': 0, 'protein': 0, 'fats': 0, 'carbs': 0, 'fiber': 0,
        'sugar': 0, 'liquid_ml': ml, 'liquid_type': 'water', 'alcohol_type': 'none',
    }]
    async with async_session() as session:
        entry = CalorieEntry(user_id=user.telegram_id, source_type='button')
        _apply_items(entry, items, 'none')
        session.add(entry)
        await session.commit()
        return entry.id


async def get_entry(kind: str, entry_id: int, user_id: int, include_deleted: bool = False):
    model = CalorieEntry if kind == 'f' else WorkoutEntry
    async with async_session() as session:
        entry = await session.get(model, entry_id)
    if not entry or entry.user_id != user_id:
        return None
    if entry.deleted_at and not include_deleted:
        return None
    return entry


async def update_entry(kind: str, entry_id: int, user: User, result: Dict) -> bool:
    """Заменить данные записи результатом нового разбора (дата записи не меняется)"""
    model = CalorieEntry if kind == 'f' else WorkoutEntry
    async with async_session() as session:
        entry = await session.get(model, entry_id)
        if not entry or entry.user_id != user.telegram_id or entry.deleted_at:
            return False
        if kind == 'f':
            if not result['items']:
                return False
            _apply_items(entry, result['items'], result.get('meal_type') or entry.meal_type or 'none')
            entry.ai_notes = None
        else:
            if not result['workouts']:
                return False
            _apply_workout(entry, result['workouts'][0], user.weight or 70)
        await session.commit()
    return True


QUICK_FIELDS = {
    'calories': ('калори', 'ккал'),
    'protein': ('белк', 'белок'),
    'fats': ('жир',),
    'carbs': ('углевод',),
    'fiber': ('клетчат',),
    'sugar': ('сахар',),
    'duration': ('минут', 'мин'),
}


def parse_quick_edit(text: str) -> Dict[str, float]:
    """
    Быстрая правка числа: «калории 400», «белки: 30», «45 минут».
    Возвращает {поле: значение}; пусто — если это не быстрая правка.
    """
    import re
    found: Dict[str, float] = {}
    rest = text.lower()
    for field, stems in QUICK_FIELDS.items():
        stem = '|'.join(stems)
        patterns = (rf'(?:{stem})[а-я]*\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)',
                    rf'(\d+(?:[.,]\d+)?)\s*(?:г\s*|грамм\w*\s*)?(?:{stem})[а-я]*')
        for pattern in patterns:
            match = re.search(pattern, rest)
            if match:
                found[field] = float(match.group(1).replace(',', '.'))
                rest = rest[:match.start()] + ' ' + rest[match.end():]
                break
    # Если осталось что-то кроме разделителей — это не быстрая правка, а описание для AI
    if not found or re.search(r'[a-zа-яё0-9]', rest):
        return {}
    return found


async def apply_quick_edit(kind: str, entry_id: int, user: User, fields: Dict[str, float]) -> bool:
    model = CalorieEntry if kind == 'f' else WorkoutEntry
    async with async_session() as session:
        entry = await session.get(model, entry_id)
        if not entry or entry.user_id != user.telegram_id or entry.deleted_at:
            return False
        if kind == 'f':
            limits = {'calories': 5000, 'protein': 300, 'fats': 300, 'carbs': 500, 'fiber': 100, 'sugar': 300}
            changed = False
            for field, value in fields.items():
                if field in limits and 0 <= value <= limits[field]:
                    setattr(entry, field, int(value) if field == 'calories' else value)
                    changed = True
            if not changed:
                return False
            entry.ai_notes = 'manual_edit'
        else:
            duration = fields.get('duration')
            if not duration or not 1 <= duration <= 600:
                return False
            entry.duration = int(duration)
            if entry.met:
                entry.calories_burned = nutrition.workout_calories(entry.met, user.weight or 70, entry.duration)
        await session.commit()
    return True


async def set_deleted(kind: str, entry_id: int, user_id: int, deleted: bool):
    """Мягкое удаление / восстановление. Возвращает запись или None"""
    model = CalorieEntry if kind == 'f' else WorkoutEntry
    async with async_session() as session:
        entry = await session.get(model, entry_id)
        if not entry or entry.user_id != user_id:
            return None
        if deleted:
            if entry.deleted_at:
                return None
            entry.deleted_at = utc_now()
        else:
            if not entry.deleted_at or utc_now() - entry.deleted_at > UNDO_WINDOW:
                return None
            entry.deleted_at = None
        await session.commit()
        return entry


def entry_title(kind: str, entry) -> str:
    if kind == 'f':
        return escape(entry.food_name)
    return escape(entry.workout_type)


def entry_details(kind: str, entry, user: User) -> str:
    """Подробности одной записи"""
    time_text = to_local(entry.created_at, user).strftime('%d.%m %H:%M')
    if kind == 'w':
        lines = [f"🏃 <b>{escape(entry.workout_type)}</b>", f"🕐 {time_text}", f"⏱ {entry.duration} мин"]
        if entry.source_type == 'watch':
            lines[0] += " ⌚"
            if entry.started_at and entry.ended_at:
                lines[1] = f"🕐 {to_local(entry.started_at, user):%d.%m %H:%M}–{to_local(entry.ended_at, user):%H:%M}"
            if entry.avg_hr:
                lines.append(f"❤️ Пульс {int(entry.avg_hr)}" + (f", максимум {int(entry.max_hr)}" if entry.max_hr else ""))
        if entry.distance:
            lines.append(f"📏 {nutrition.fmt(entry.distance)} км")
        if entry.met:
            lines.append(f"🔥 {nutrition.workout_formula(entry.met, user.weight or 70, entry.duration)} ккал")
        else:
            lines.append(f"🔥 {entry.calories_burned} ккал" + (" — по данным часов" if entry.source_type == 'watch' else ""))
        return "\n".join(lines)

    lines = [f"🍽 <b>{escape(entry.food_name)}</b>", f"🕐 {time_text}", ""]
    items = [] if entry.ai_notes == 'manual_edit' else (entry.items or [])
    for item in items:
        line = f"• {escape(item['name'])} — {item['calories']} ккал"
        if item.get('liquid_ml') and item.get('liquid_type') != 'none':
            line += f", {item['liquid_ml']} мл"
        lines.append(line)
    if items:
        lines.append("")
    fmt = nutrition.fmt
    lines.append(
        f"🔥 {entry.calories} ккал · 🥩 {fmt(entry.protein or 0)} · 🧈 {fmt(entry.fats or 0)} · "
        f"🍞 {fmt(entry.carbs or 0)} · 🌾 {fmt(entry.fiber or 0)} · 🍬 {fmt(entry.sugar or 0)} г"
    )
    liquid = (entry.water_ml or 0) + (entry.drinks_ml or 0) + (entry.soup_ml or 0)
    if liquid:
        lines.append(f"💧 Жидкость: {liquid} мл")
    alcohol = nutrition.alcohol_line({d['type']: d['ml'] for d in entry.alcohol or []})
    if alcohol:
        lines.append(alcohol)
    if entry.ai_notes == 'manual_edit':
        lines.append("<i>изменено вручную</i>")
    return "\n".join(lines)


def previous_result(kind: str, entry) -> Dict:
    """Данные записи в формате разбора AI — контекст для исправления"""
    if kind == 'w':
        return {'items': [], 'workouts': [{
            'name': entry.workout_type, 'duration_min': entry.duration,
            'met': entry.met or 0, 'distance_km': entry.distance or 0,
        }]}
    items = entry.items or [{
        'name': entry.food_name, 'calories': entry.calories, 'protein': entry.protein or 0,
        'fats': entry.fats or 0, 'carbs': entry.carbs or 0, 'fiber': entry.fiber or 0,
        'sugar': entry.sugar or 0, 'liquid_ml': 0, 'liquid_type': 'none', 'alcohol_type': 'none',
    }]
    return {'items': items, 'workouts': []}


async def day_report_text(user: User, days_ago: int = 0) -> Tuple[str, List[Tuple[int, str, int]], bool]:
    """
    Полный отчёт за день + список записей.
    Возвращает (текст, [(номер, kind, id)], есть ли данные с часов за этот день).
    """
    entries, workouts = await load_day(user, days_ago)
    norms = nutrition.daily_norms(user)
    totals = nutrition.day_totals(entries, workouts)
    metrics = await health.day_metrics(user, days_ago)
    watch = health.watch_energy(user, metrics, workouts)
    has_watch = bool(metrics) or any(w.source_type == 'watch' for w in workouts)
    text = nutrition.day_report(totals, norms, workouts, user.weight or 70, day_label(user, days_ago), watch)

    rows = sorted(
        [('f', e) for e in entries] + [('w', w) for w in workouts],
        key=lambda pair: pair[1].created_at
    )
    buttons = []
    if rows:
        lines = ["", "<b>Записи:</b>"]
        for number, (kind, entry) in enumerate(rows, start=1):
            time_text = to_local(entry.created_at, user).strftime('%H:%M')
            if kind == 'f':
                liquid = (entry.water_ml or 0) + (entry.drinks_ml or 0) + (entry.soup_ml or 0)
                extra = f"{entry.calories} ккал" if entry.calories else ""
                if liquid:
                    extra += (" · " if extra else "") + f"{liquid} мл"
                name = escape(entry.food_name[:60])
            else:
                extra = f"🔥 {entry.calories_burned} ккал"
                name = f"{'⌚ ' if entry.source_type == 'watch' else ''}{escape(entry.workout_type)}, {entry.duration} мин"
            lines.append(f"{number}. {time_text} {name} — {extra}")
            buttons.append((number, kind, entry.id))
        lines.append("\n<i>Нажми на номер, чтобы исправить или удалить запись.</i>")
        listing = "\n".join(lines)
        # Ограничение Telegram — 4096 символов
        if len(text) + len(listing) > 4000:
            listing = listing[:max(0, 3990 - len(text))] + "…"
        text += "\n" + listing
    else:
        text += "\n\n<i>За этот день записей нет.</i>"
    return text, buttons, has_watch


async def day_brief_text(user: User) -> str:
    """Короткая сводка за сегодня — после добавления записи"""
    entries, workouts = await load_day(user)
    norms = nutrition.daily_norms(user)
    totals = nutrition.day_totals(entries, workouts)
    watch = health.watch_energy(user, await health.day_metrics(user), workouts)
    return nutrition.day_brief(totals, norms, watch)


async def liquid_brief_text(user: User) -> str:
    entries, workouts = await load_day(user)
    norms = nutrition.daily_norms(user)
    totals = nutrition.day_totals(entries, workouts)
    return nutrition.liquid_brief(totals, norms)
