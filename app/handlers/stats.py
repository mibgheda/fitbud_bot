from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, cast, Date
from datetime import datetime, timedelta

from database.database import async_session, CalorieEntry, WorkoutEntry, WeightLog, User
from keyboards.reply import get_main_menu, not_menu_button
from utils import diary, nutrition
from utils.daytime import day_bounds

router = Router()


class AddWeight(StatesGroup):
    """Состояние для добавления веса"""
    waiting_for_weight = State()


@router.message(F.text == "📈 Моя статистика")
async def show_statistics(message: Message, state: FSMContext):
    """Статистика: сегодня кратко, неделя и месяц"""
    await state.clear()
    from handlers.ai_hub import ensure_ready
    user = await ensure_ready(message, state)
    if not user:
        return
    user_id = message.from_user.id
    week_start = day_bounds(user, 6)[0]
    month_start = day_bounds(user, 29)[0]
    norms = nutrition.daily_norms(user)

    async with async_session() as session:
        # Дневные суммы за неделю (без воды) — средние по дням с записями
        week_meals = (await session.execute(
            select(CalorieEntry)
            .where(CalorieEntry.user_id == user_id)
            .where(CalorieEntry.created_at >= week_start)
            .where(CalorieEntry.deleted_at.is_(None))
        )).scalars().all()

        workout_week = (await session.execute(
            select(func.count(WorkoutEntry.id), func.sum(WorkoutEntry.duration), func.sum(WorkoutEntry.calories_burned))
            .where(WorkoutEntry.user_id == user_id)
            .where(WorkoutEntry.created_at >= week_start)
            .where(WorkoutEntry.deleted_at.is_(None))
        )).one()
        workout_month = (await session.execute(
            select(func.count(WorkoutEntry.id), func.sum(WorkoutEntry.duration))
            .where(WorkoutEntry.user_id == user_id)
            .where(WorkoutEntry.created_at >= month_start)
            .where(WorkoutEntry.deleted_at.is_(None))
        )).one()

        weight_data = (await session.execute(
            select(WeightLog.weight, WeightLog.created_at)
            .where(WeightLog.user_id == user_id)
            .order_by(WeightLog.created_at.desc())
            .limit(2)
        )).all()

    # Группируем еду по «дням пользователя»
    days = {}
    for entry in week_meals:
        for days_ago in range(7):
            start, end = day_bounds(user, days_ago)
            if start <= entry.created_at < end:
                day = days.setdefault(days_ago, {'calories': 0, 'protein': 0, 'fiber': 0, 'meals': 0})
                day['calories'] += entry.calories or 0
                day['protein'] += entry.protein or 0
                day['fiber'] += entry.fiber or 0
                if entry.meal_type != 'water':
                    day['meals'] += 1
                break
    food_days = [d for d in days.values() if d['meals']]
    meals_week = sum(d['meals'] for d in food_days)
    count = len(food_days) or 1
    avg_kcal = int(sum(d['calories'] for d in food_days) / count)
    avg_protein = int(sum(d['protein'] for d in food_days) / count)
    avg_fiber = int(sum(d['fiber'] for d in food_days) / count)
    protein_days = sum(1 for d in food_days if d['protein'] >= norms['protein'])
    fiber_days = sum(1 for d in food_days if d['fiber'] >= norms['fiber'])

    workouts_week, duration_week, burned_week = (v or 0 for v in workout_week)
    workouts_month, duration_month = (v or 0 for v in workout_month)

    weight_progress = ""
    if len(weight_data) >= 2:
        diff = weight_data[0][0] - weight_data[1][0]
        change = f"+{diff:.1f} кг" if diff > 0 else (f"{diff:.1f} кг" if diff < 0 else "без изменений")
        weight_progress = f"\n⚖️ Вес: {weight_data[0][0]} кг ({change})"
    elif weight_data:
        weight_progress = f"\n⚖️ Вес: {weight_data[0][0]} кг"

    stats_text = (
        f"📈 <b>Твоя статистика</b>\n\n"
        f"{await diary.day_brief_text(user)}\n\n"
        f"<b>📆 За 7 дней</b> (дней с записями: {len(food_days)}):\n"
        f"Приёмов пищи: <b>{meals_week}</b>\n"
        f"В среднем: <b>{avg_kcal}</b> ккал · 🥩 <b>{avg_protein}</b> г · 🌾 <b>{avg_fiber}</b> г в день\n"
        f"Белок добран: <b>{protein_days}</b> дн. · клетчатка: <b>{fiber_days}</b> дн.\n"
        f"Тренировок: <b>{workouts_week}</b> · {duration_week} мин · 🔥 {burned_week} ккал\n\n"
        f"<b>📅 За 30 дней:</b>\n"
        f"Тренировок: <b>{workouts_month}</b> · {duration_month} мин"
        f"{weight_progress}\n\n"
        "<i>Подробно по дням — «📋 Мой день»</i>"
    )
    await message.answer(stats_text, reply_markup=get_main_menu())


@router.message(F.text == "⚖️ Записать вес")
async def start_add_weight(message: Message, state: FSMContext):
    """Начать добавление веса"""
    await state.clear()
    await message.answer(
        "Введи свой текущий вес в килограммах:\n\n"
        "Например: <i>72.5</i>"
    )
    await state.set_state(AddWeight.waiting_for_weight)


@router.message(AddWeight.waiting_for_weight, not_menu_button)
async def process_weight(message: Message, state: FSMContext):
    """Обработка и сохранение веса"""
    try:
        weight = float(message.text.replace(',', '.'))
        if weight < 30 or weight > 300:
            await message.answer("Пожалуйста, введи корректный вес (от 30 до 300 кг)")
            return

        async with async_session() as session:
            # Сохраняем запись о весе
            weight_log = WeightLog(
                user_id=message.from_user.id,
                weight=weight
            )
            session.add(weight_log)

            # Обновляем вес в профиле
            user_result = await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = user_result.scalar_one_or_none()

            old_weight = None
            weight_history = []
            if user:
                old_weight = user.weight
                user.weight = weight
                # Нормы зависят от веса — пересчитываем
                if user.daily_calorie_target and user.age and user.height and user.gender:
                    user.daily_calorie_target = nutrition.calculate_calories(
                        user.gender, weight, user.height, user.age,
                        user.activity_level or 'moderate', user.goal or 'maintain'
                    )

                # Получаем предыдущие записи для статистики
                prev_weights = await session.execute(
                    select(WeightLog.weight, WeightLog.created_at)
                    .where(WeightLog.user_id == message.from_user.id)
                    .order_by(WeightLog.created_at.desc())
                    .limit(5)
                )
                weight_history = prev_weights.all()

            await session.commit()

        # Формируем сообщение
        response = f"✅ Вес записан: <b>{weight} кг</b>\n\n"

        if old_weight and old_weight != weight:
            diff = weight - old_weight
            if diff > 0:
                response += f"Изменение: <b>+{diff:.1f} кг</b> 📈\n"
            else:
                response += f"Изменение: <b>{diff:.1f} кг</b> 📉\n"

        if len(weight_history) > 1:
            response += f"\n📊 <b>История веса:</b>\n"
            for w, date in weight_history[:5]:
                date_str = date.strftime("%d.%m.%Y")
                response += f"{date_str}: {w} кг\n"

        if user and user.daily_calorie_target:
            response += f"\n<b>Нормы пересчитаны:</b>\n{nutrition.norms_text(nutrition.daily_norms(user))}"
        await message.answer(response, reply_markup=get_main_menu())
        await state.clear()

    except ValueError:
        await message.answer("Пожалуйста, введи вес числом (можно с десятичной точкой)")
