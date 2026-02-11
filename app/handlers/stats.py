from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from datetime import datetime, timedelta

from database.database import async_session, CalorieEntry, WorkoutEntry, WeightLog, User, calc_today_start
from keyboards.reply import get_main_menu, not_menu_button

router = Router()


class AddWeight(StatesGroup):
    """Состояние для добавления веса"""
    waiting_for_weight = State()


@router.message(F.text == "📈 Моя статистика")
async def show_statistics(message: Message, state: FSMContext):
    """Показать статистику пользователя"""
    await state.clear()
    async with async_session() as session:
        # Получаем данные пользователя для /new_day и целевой калорийности
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        today_start = calc_today_start(user.current_day_start if user else None)
        week_ago = datetime.now() - timedelta(days=7)
        month_ago = datetime.now() - timedelta(days=30)

        # Статистика по калориям за сегодня
        cal_today = await session.execute(
            select(func.sum(CalorieEntry.calories))
            .where(CalorieEntry.user_id == message.from_user.id)
            .where(CalorieEntry.created_at >= today_start)
        )
        calories_today = cal_today.scalar() or 0

        # Статистика по калориям за неделю
        cal_week = await session.execute(
            select(
                func.count(CalorieEntry.id),
                func.avg(CalorieEntry.calories)
            )
            .where(CalorieEntry.user_id == message.from_user.id)
            .where(CalorieEntry.created_at >= week_ago)
        )
        meals_week, avg_week = cal_week.one()
        meals_week = meals_week or 0
        avg_week = int(avg_week) if avg_week else 0

        # Статистика по тренировкам за неделю
        workout_week = await session.execute(
            select(
                func.count(WorkoutEntry.id),
                func.sum(WorkoutEntry.duration),
                func.sum(WorkoutEntry.calories_burned)
            )
            .where(WorkoutEntry.user_id == message.from_user.id)
            .where(WorkoutEntry.created_at >= week_ago)
        )
        workouts_week, duration_week, burned_week = workout_week.one()
        workouts_week = workouts_week or 0
        duration_week = duration_week or 0
        burned_week = burned_week or 0

        # Статистика по тренировкам за месяц
        workout_month = await session.execute(
            select(
                func.count(WorkoutEntry.id),
                func.sum(WorkoutEntry.duration)
            )
            .where(WorkoutEntry.user_id == message.from_user.id)
            .where(WorkoutEntry.created_at >= month_ago)
        )
        workouts_month, duration_month = workout_month.one()
        workouts_month = workouts_month or 0
        duration_month = duration_month or 0

        # Целевая калорийность (уже получили user выше)
        target = user.daily_calorie_target if user and user.daily_calorie_target else 2000

        # Прогресс по весу
        weight_logs = await session.execute(
            select(WeightLog.weight, WeightLog.created_at)
            .where(WeightLog.user_id == message.from_user.id)
            .order_by(WeightLog.created_at.desc())
            .limit(2)
        )
        weight_data = weight_logs.all()

        weight_progress = ""
        if len(weight_data) >= 2:
            current_weight = weight_data[0][0]
            previous_weight = weight_data[1][0]
            weight_diff = current_weight - previous_weight
            if weight_diff > 0:
                weight_progress = f"\n📊 Вес: {current_weight} кг (+{weight_diff:.1f} кг)"
            elif weight_diff < 0:
                weight_progress = f"\n📊 Вес: {current_weight} кг ({weight_diff:.1f} кг)"
            else:
                weight_progress = f"\n📊 Вес: {current_weight} кг (без изменений)"
        elif len(weight_data) == 1:
            weight_progress = f"\n📊 Вес: {weight_data[0][0]} кг"

        # Формируем сообщение
        remaining = target - calories_today
        progress_percent = min(100, int((calories_today / target) * 100))
        progress_bar = "█" * (progress_percent // 10) + "░" * (10 - progress_percent // 10)

        stats_text = (
            f"📊 <b>Твоя статистика</b>\n\n"
            f"<b>📅 Сегодня:</b>\n"
            f"{progress_bar} {progress_percent}%\n"
            f"Калории: <b>{calories_today}</b> / {target} ккал\n"
            f"Осталось: <b>{remaining}</b> ккал\n\n"
            f"<b>📆 За неделю:</b>\n"
            f"Приемов пищи: <b>{meals_week}</b>\n"
            f"Средняя калорийность: <b>{avg_week}</b> ккал/день\n"
            f"Тренировок: <b>{workouts_week}</b>\n"
            f"Время тренировок: <b>{duration_week}</b> мин\n"
            f"Сожжено калорий: <b>~{burned_week}</b> ккал\n\n"
            f"<b>📈 За месяц:</b>\n"
            f"Тренировок: <b>{workouts_month}</b>\n"
            f"Время тренировок: <b>{duration_month}</b> мин"
        )

        if weight_progress:
            stats_text += f"\n{weight_progress}"

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

        await message.answer(response, reply_markup=get_main_menu())
        await state.clear()

    except ValueError:
        await message.answer("Пожалуйста, введи вес числом (можно с десятичной точкой)")
