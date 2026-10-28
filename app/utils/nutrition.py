"""
Нормы КБЖУ, клетчатки, сахара и жидкости, расчёт сожжённых калорий и тексты отчётов.

Здесь нет обращений к AI: всё считается кодом по данным, которые AI уже вернул
и которые прошли проверку. Поэтому советы и предупреждения не зависят от
текста пользователя и не поддаются prompt injection.
"""
import math
from html import escape
from typing import Dict, List, Optional

# Белок, г на кг веса — по цели (можно переопределить в профиле)
PROTEIN_PER_KG = {'lose_weight': 1.8, 'maintain': 1.4, 'gain_weight': 1.8}
PROTEIN_PER_KG_RANGE = (0.8, 3.0)

FAT_SHARE = 0.30  # жиры — 30% калорий (максимум)
SUGAR_SHARE = 0.10  # добавленный сахар — до 10% калорий (рекомендация ВОЗ)
FIBER_PER_1000_KCAL = 14
FIBER_MIN = 25
LIQUID_ML_PER_KG = 30

# Доля дневного лимита за один приём пищи: до 40% — норм, 40–60% — многовато, больше — перебор
MEAL_WARN_SHARE = 0.40
MEAL_ALERT_SHARE = 0.60

# В жидкость засчитывается треть объёма супа
SOUP_LIQUID_SHARE = 1 / 3

# Активность вне тренировок — тренировки прибавляются отдельно
ACTIVITY_MULTIPLIERS = {'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55}
ACTIVITY_LABELS = {
    'sedentary': 'Сидячая работа',
    'light': 'Много хожу, на ногах',
    'moderate': 'Физический труд',
}
GOAL_LABELS = {
    'lose_weight': 'Похудение',
    'maintain': 'Поддержание веса',
    'gain_weight': 'Набор массы',
}

ALCOHOL_TYPES = {
    # тип: (эмодзи, объём одной порции в мл, подпись)
    'wine': ('🍷', 150, 'вино'),
    'champagne': ('🥂', 150, 'игристое'),
    'beer': ('🍺', 500, 'пиво'),
    'spirits': ('🥃', 50, 'крепкое'),
    'cocktail': ('🍸', 200, 'коктейли'),
    'other': ('🍹', 150, 'другое'),
}


# ==================== Нормы ====================

def calculate_calories(gender: str, weight: float, height: int, age: int,
                       activity_level: str = 'sedentary', goal: str = 'maintain') -> int:
    """Суточная норма калорий без тренировок (Миффлин–Сан Жеор)"""
    if gender == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    # Старые уровни активности учитывали тренировки — приводим к «физическому труду»
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(activity_level, 1.55)
    if goal == 'lose_weight':
        return int(tdee - 500)
    if goal == 'gain_weight':
        return int(tdee + 300)
    return int(tdee)


def bmr(user) -> float:
    """Основной обмен (Миффлин–Сан Жеор)"""
    base = 10 * (user.weight or 70) + 6.25 * (user.height or 170) - 5 * (user.age or 30)
    return base + 5 if user.gender == 'male' else base - 161


def watch_base_calories(user) -> int:
    """
    База для дней с часами: обмен × 1,2 ± цель. Всё движение за день (шаги, тренировки)
    прибавляется отдельно — из активных калорий Apple Watch.
    """
    base = bmr(user) * 1.2
    if user.goal == 'lose_weight':
        base -= 500
    elif user.goal == 'gain_weight':
        base += 300
    return int(base)


def fmt(value: float) -> str:
    """Число по-русски: 2,2 вместо 2.2"""
    return f"{value:g}".replace('.', ',')


def protein_per_kg(user) -> float:
    custom = getattr(user, 'protein_per_kg', None)
    if custom:
        return custom
    return PROTEIN_PER_KG.get(getattr(user, 'goal', None), 1.4)


def daily_norms(user) -> Dict[str, float]:
    """Дневные нормы пользователя (без учёта тренировок)"""
    kcal = user.daily_calorie_target or 2000
    weight = user.weight or 70
    protein = round(weight * protein_per_kg(user))
    fats = round(kcal * FAT_SHARE / 9)
    carbs = max(0, round((kcal - protein * 4 - fats * 9) / 4))
    return {
        'calories': kcal,
        'protein': protein,  # минимум
        'fiber': max(FIBER_MIN, round(kcal / 1000 * FIBER_PER_1000_KCAL)),  # минимум
        'fats': fats,  # максимум
        'carbs': carbs,  # максимум
        'sugar': round(kcal * SUGAR_SHARE / 4),  # максимум
        'liquid': int(round(weight * LIQUID_ML_PER_KG / 50.0)) * 50,
    }


# ==================== Подсчёт ====================

def workout_calories(met: float, weight: float, duration_min: float) -> int:
    """Сожжённые калории: MET × вес (кг) × время (ч)"""
    return int(round(met * weight * duration_min / 60))


def workout_formula(met: float, weight: float, duration_min: float) -> str:
    hours = duration_min / 60
    hours_text = f"{hours:.2f}".rstrip('0').rstrip('.').replace('.', ',')
    met_text = f"{met:g}".replace('.', ',')
    weight_text = f"{weight:g}".replace('.', ',')
    return f"{met_text} MET × {weight_text} кг × {hours_text} ч = {workout_calories(met, weight, duration_min)}"


def meal_totals(items: List[Dict]) -> Dict:
    """Итоги приёма пищи по списку продуктов"""
    totals = {key: 0.0 for key in ('calories', 'protein', 'fats', 'carbs', 'fiber', 'sugar')}
    water_ml = drinks_ml = soup_ml = 0
    alcohol: Dict[str, int] = {}
    for item in items:
        for key in totals:
            totals[key] += item.get(key, 0) or 0
        liquid = int(item.get('liquid_ml', 0) or 0)
        kind = item.get('liquid_type', 'none')
        if kind == 'water':
            water_ml += liquid
        elif kind == 'drink':
            drinks_ml += liquid
        elif kind == 'soup':
            soup_ml += int(round(liquid * SOUP_LIQUID_SHARE))
        elif kind == 'alcohol' and liquid:
            alcohol_type = item.get('alcohol_type', 'other')
            alcohol[alcohol_type] = alcohol.get(alcohol_type, 0) + liquid
    totals['calories'] = int(round(totals['calories']))
    for key in ('protein', 'fats', 'carbs', 'fiber', 'sugar'):
        totals[key] = round(totals[key], 1)
    totals.update(
        water_ml=water_ml, drinks_ml=drinks_ml, soup_ml=soup_ml,
        alcohol=[{'type': t, 'ml': ml} for t, ml in alcohol.items()],
    )
    return totals


def is_water_only(items: List[Dict]) -> bool:
    """Сообщение только про воду — записываем без подтверждения"""
    return bool(items) and all(
        item.get('liquid_type') == 'water' and (item.get('calories') or 0) < 1 for item in items
    )


def day_totals(entries, workouts) -> Dict:
    """Итоги дня по записям из базы"""
    totals = {key: 0.0 for key in ('calories', 'protein', 'fats', 'carbs', 'fiber', 'sugar')}
    water_ml = drinks_ml = soup_ml = 0
    alcohol: Dict[str, int] = {}
    for entry in entries:
        for key in totals:
            totals[key] += getattr(entry, key, 0) or 0
        water_ml += entry.water_ml or 0
        drinks_ml += entry.drinks_ml or 0
        soup_ml += entry.soup_ml or 0
        for drink in entry.alcohol or []:
            alcohol[drink.get('type', 'other')] = alcohol.get(drink.get('type', 'other'), 0) + int(drink.get('ml', 0))
    totals['burned'] = sum(w.calories_burned or 0 for w in workouts)
    totals.update(water_ml=water_ml, drinks_ml=drinks_ml, soup_ml=soup_ml, alcohol=alcohol)
    return totals


# ==================== Оформление ====================

def _num(value: float) -> str:
    return f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}".replace('.', ',')


def progress_bar(value: float, target: float, width: int = 10) -> str:
    if not target:
        return '░' * width
    filled = min(width, int(value / target * width))
    return '▓' * filled + '░' * (width - filled)


def alcohol_line(alcohol: Dict[str, int]) -> Optional[str]:
    if not alcohol:
        return None
    parts = []
    for alcohol_type, ml in alcohol.items():
        emoji, portion, label = ALCOHOL_TYPES.get(alcohol_type, ALCOHOL_TYPES['other'])
        count = min(10, max(1, math.ceil(ml / portion)))
        parts.append(f"{emoji * count} {ml} мл ({label})")
    return "🍸 <b>Алкоголь:</b> " + " · ".join(parts) + "\n<i>в жидкость не засчитывается</i>"


def _meal_share_mark(share: float) -> str:
    if share > MEAL_ALERT_SHARE:
        return "🔴"
    if share > MEAL_WARN_SHARE:
        return "🟡"
    return "🟢"


def meal_report(totals: Dict, norms: Dict) -> str:
    """КБЖУ приёма пищи с оценкой «не перебор ли за один раз»"""
    lines = [f"🔥 <b>{totals['calories']} ккал</b>", ""]

    for key, emoji, label in (('protein', '🥩', 'Белки'), ('fiber', '🌾', 'Клетчатка')):
        value = totals[key]
        share = value / norms[key] if norms[key] else 0
        lines.append(f"{emoji} {label}: <b>{_num(value)} г</b> — {int(share * 100)}% дневной нормы")

    alerts = []
    for key, emoji, label in (('fats', '🧈', 'Жиры'), ('carbs', '🍞', 'Углеводы'), ('sugar', '🍬', 'Сахар')):
        value = totals[key]
        share = value / norms[key] if norms[key] else 0
        mark = _meal_share_mark(share)
        lines.append(f"{emoji} {label}: <b>{_num(value)} г</b> {mark} {int(share * 100)}% дневного лимита")
        if share > MEAL_ALERT_SHARE:
            alerts.append(label.lower())

    liquid = totals['water_ml'] + totals['drinks_ml'] + totals['soup_ml']
    if liquid:
        lines.append(f"💧 Жидкость: <b>{liquid} мл</b>")
    alcohol = {d['type']: d['ml'] for d in totals.get('alcohol', [])}
    if alcohol:
        lines.append(alcohol_line(alcohol))

    if alerts:
        lines.append("")
        lines.append(f"⚠️ <b>{', '.join(alerts).capitalize()}</b> за один приём — больше половины дневного лимита.")
    return "\n".join(lines)


def _tips(totals: Dict, norms: Dict) -> List[str]:
    """Советы по итогам дня — фиксированные шаблоны, не текст AI"""
    tips = []
    protein_left = norms['protein'] - totals['protein']
    fats_share = totals['fats'] / norms['fats'] if norms['fats'] else 0
    if protein_left > 15:
        if fats_share >= 0.8:
            tips.append("Добери белок без лишних жиров: творог 0–5%, куриная грудка, белая рыба, яичные белки.")
        else:
            tips.append("Добери белок: мясо, рыба, яйца, творог, бобовые.")
    if norms['fiber'] - totals['fiber'] > 5:
        tips.append("Клетчатки мало: овощи, зелень, ягоды, бобовые, цельнозерновой хлеб, отруби.")
    if norms['sugar'] and totals['sugar'] > norms['sugar']:
        tips.append("Сахар сверх нормы — сладкое сегодня лучше больше не есть.")
    return tips[:2]


def _workout_line(w, user_weight: float) -> str:
    if w.met:
        return f"   • {escape(w.workout_type)}, {w.duration} мин: {workout_formula(w.met, user_weight, w.duration)}"
    mark = " ⌚" if getattr(w, 'source_type', None) == 'watch' else ""
    return f"   • {escape(w.workout_type)}, {w.duration} мин: {w.calories_burned}{mark}"


def day_report(totals: Dict, norms: Dict, workouts, user_weight: float, title: str,
               watch: Optional[Dict] = None) -> str:
    """
    Отчёт за день: что добрать и что не перебрать.
    watch — энергия с часов (utils.health.watch_energy): тогда норма = база + активность с часов.
    """
    lines = [f"📊 <b>{escape(title)}</b>", ""]
    eaten = int(totals['calories'])
    if watch:
        base = watch['base']
        burned = watch['active'] + watch['manual_kcal']
        kcal_limit = base + burned
        lines.append(f"🎯 База: <b>{base}</b> ккал  <i>(обмен × 1,2 ± цель)</i>")
        lines.append(f"🍽 Съедено: <b>{eaten}</b> ккал")
        lines.append(f"⌚ Активность с часов: <b>+{watch['active']}</b> ккал")
        for w in watch['watch_workouts']:
            lines.append(f"   🏃 {escape(w.workout_type)}, {w.duration} мин — {w.calories_burned}")
        steps = f" ({watch['steps']:,} шагов)".replace(',', ' ') if watch['steps'] else ""
        lines.append(f"   👟 Шаги и движение{steps} — {watch['movement']}")
        if watch['manual_workouts']:
            lines.append(f"✍️ Тренировки без часов: <b>+{watch['manual_kcal']}</b> ккал")
            lines += [_workout_line(w, user_weight) for w in watch['manual_workouts']]
        formula = f"{base} − {eaten} + {watch['active']}" + (f" + {watch['manual_kcal']}" if watch['manual_kcal'] else "")
    else:
        burned = totals['burned']
        kcal_limit = norms['calories'] + burned
        lines.append(f"🎯 Норма: <b>{norms['calories']}</b> ккал")
        lines.append(f"🍽 Съедено: <b>{eaten}</b> ккал")
        if workouts:
            lines.append(f"🔥 Сожжено: <b>+{burned}</b> ккал")
            lines += [_workout_line(w, user_weight) for w in workouts]
        formula = f"{norms['calories']} − {eaten}" + (f" + {burned}" if burned else "")
    left = kcal_limit - totals['calories']
    sign = "Осталось" if left >= 0 else "Перебор"
    lines.append(f"{'✅' if left >= 0 else '🔴'} {sign}: <b>{abs(int(left))}</b> ккал  <i>({formula})</i>")
    lines.append(progress_bar(totals['calories'], kcal_limit))

    lines += ["", "<b>Добрать:</b>"]
    for key, emoji, label in (('protein', '🥩', 'Белки'), ('fiber', '🌾', 'Клетчатка')):
        value, target = totals[key], norms[key]
        status = "✅" if value >= target else f"❗ ещё {_num(target - value)} г"
        lines.append(f"{emoji} {label}: <b>{_num(value)}</b> / {target} г  {progress_bar(value, target)}  {status}")

    lines += ["", "<b>Не перебрать:</b>"]
    for key, emoji, label in (('fats', '🧈', 'Жиры'), ('carbs', '🍞', 'Углеводы'), ('sugar', '🍬', 'Сахар')):
        value, target = totals[key], norms[key]
        share = value / target if target else 0
        status = "🔴 перебор" if share > 1 else ("🟡 почти лимит" if share >= 0.8 else "🟢")
        lines.append(f"{emoji} {label}: <b>{_num(value)}</b> / {target} г  {progress_bar(value, target)}  {status}")

    liquid = totals['water_ml'] + totals['drinks_ml'] + totals['soup_ml']
    lines.append("")
    lines.append(f"💧 <b>Жидкость:</b> {liquid} / {norms['liquid']} мл  {progress_bar(liquid, norms['liquid'])}")
    parts = []
    if totals['water_ml']:
        parts.append(f"вода {totals['water_ml']}")
    if totals['drinks_ml']:
        parts.append(f"напитки {totals['drinks_ml']}")
    if totals['soup_ml']:
        parts.append(f"суп {totals['soup_ml']} (треть объёма)")
    if parts:
        lines.append("   " + " · ".join(parts))
    alcohol = alcohol_line(totals['alcohol'])
    if alcohol:
        lines.append(alcohol)

    tips = _tips(totals, norms) if totals['calories'] else []
    if tips:
        lines.append("")
        lines += [f"💡 {tip}" for tip in tips]
    lines.append("")
    lines.append("<i>Клетчатка и сахар — оценка ИИ, ±20%</i>")
    return "\n".join(lines)


def norms_text(norms: Dict) -> str:
    return (
        f"🔥 Калории: <b>{norms['calories']}</b> ккал + сожжённое на тренировках\n"
        f"🥩 Белки: <b>от {norms['protein']}</b> г\n"
        f"🌾 Клетчатка: <b>от {norms['fiber']}</b> г\n"
        f"🧈 Жиры: <b>до {norms['fats']}</b> г\n"
        f"🍞 Углеводы: <b>до {norms['carbs']}</b> г\n"
        f"🍬 Сахар: <b>до {norms['sugar']}</b> г\n"
        f"💧 Жидкость: <b>{norms['liquid']}</b> мл"
    )


def _liquid_parts(totals: Dict) -> str:
    parts = []
    if totals['water_ml']:
        parts.append(f"вода {totals['water_ml']}")
    if totals['drinks_ml']:
        parts.append(f"напитки {totals['drinks_ml']}")
    if totals['soup_ml']:
        parts.append(f"суп {totals['soup_ml']}")
    return " · ".join(parts)


def liquid_brief(totals: Dict, norms: Dict) -> str:
    liquid = totals['water_ml'] + totals['drinks_ml'] + totals['soup_ml']
    text = f"💧 За сегодня: <b>{liquid}</b> / {norms['liquid']} мл  {progress_bar(liquid, norms['liquid'])}"
    parts = _liquid_parts(totals)
    if parts:
        text += f"\n   {parts}"
    alcohol = alcohol_line(totals['alcohol'])
    if alcohol:
        text += f"\n{alcohol}"
    return text


def day_brief(totals: Dict, norms: Dict, watch: Optional[Dict] = None) -> str:
    """Короткая сводка дня после добавления записи"""
    if watch:
        base = watch['base']
        burned = watch['active'] + watch['manual_kcal']
        burned_text = f" + {watch['active']} ⌚" + (f" + {watch['manual_kcal']} 🔥" if watch['manual_kcal'] else "")
    else:
        base = norms['calories']
        burned = totals['burned']
        burned_text = f" + {burned} 🔥" if burned else ""
    left = base + burned - totals['calories']
    left_text = f"осталось <b>{int(left)}</b>" if left >= 0 else f"🔴 перебор <b>{int(-left)}</b>"

    def need(key: str) -> str:
        value, target = totals[key], norms[key]
        return "✅" if value >= target else f"❗ ещё {_num(target - value)}"

    def limit(key: str) -> str:
        share = totals[key] / norms[key] if norms[key] else 0
        return "🔴" if share > 1 else ("🟡" if share >= 0.8 else "🟢")

    liquid = totals['water_ml'] + totals['drinks_ml'] + totals['soup_ml']
    lines = [
        "📊 <b>За сегодня:</b>",
        f"🔥 {int(totals['calories'])} / {base}{burned_text} ккал → {left_text}",
        f"🥩 Белки {_num(totals['protein'])}/{norms['protein']} г {need('protein')} · "
        f"🌾 Клетчатка {_num(totals['fiber'])}/{norms['fiber']} г {need('fiber')}",
        f"🧈 Жиры {_num(totals['fats'])}/{norms['fats']} {limit('fats')} · "
        f"🍞 Углеводы {_num(totals['carbs'])}/{norms['carbs']} {limit('carbs')} · "
        f"🍬 Сахар {_num(totals['sugar'])}/{norms['sugar']} {limit('sugar')}",
        f"💧 Жидкость {liquid}/{norms['liquid']} мл",
    ]
    return "\n".join(lines)
