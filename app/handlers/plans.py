"""
Планы питания и тренировок — генерация AI, просмотр по дням, отметка выполнения
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func, update
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from database.database import (
    async_session, User, CalorieEntry, WorkoutEntry,
    MealPlan, MealPlanItem, WorkoutPlan, WorkoutPlanItem,
)
from keyboards.reply import (
    get_main_menu, get_meal_plan_day_keyboard,
    get_workout_plan_day_keyboard, DAY_NAMES,
)
from utils.openai_helper import generate_meal_plan, generate_workout_plan

router = Router()

MEAL_TYPE_NAMES = {
    'breakfast': '🌅 Завтрак',
    'lunch': '🌞 Обед',
    'dinner': '🌙 Ужин',
    'snack': '🍎 Перекус',
}


# ==================== Вспомогательные ====================

def get_current_week_start():
    """Понедельник текущей недели"""
    now = datetime.now()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_user_context(user_id: int) -> dict:
    """Профиль пользователя для AI + обновление last_active_at"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.last_active_at = datetime.now()
            await session.commit()
            return {
                'age': user.age,
                'gender': user.gender,
                'weight': user.weight,
                'height': user.height,
                'goal': user.goal,
                'activity_level': user.activity_level,
                'daily_target': user.daily_calorie_target,
            }
        return {}


async def get_recent_food_stats(user_id: int) -> dict:
    """Статистика питания за последнюю неделю"""
    week_ago = datetime.now() - timedelta(days=7)
    async with async_session() as session:
        result = await session.execute(
            select(
                func.avg(CalorieEntry.calories),
                func.avg(CalorieEntry.protein),
                func.avg(CalorieEntry.fats),
                func.avg(CalorieEntry.carbs),
            )
            .where(CalorieEntry.user_id == user_id)
            .where(CalorieEntry.created_at >= week_ago)
        )
        avg_cal, avg_p, avg_f, avg_c = result.one()
        return {
            'avg_calories': int(avg_cal) if avg_cal else None,
            'avg_protein': round(avg_p, 1) if avg_p else None,
            'avg_fats': round(avg_f, 1) if avg_f else None,
            'avg_carbs': round(avg_c, 1) if avg_c else None,
        }


async def get_recent_workout_stats(user_id: int) -> dict:
    """Статистика тренировок за последнюю неделю"""
    week_ago = datetime.now() - timedelta(days=7)
    async with async_session() as session:
        result = await session.execute(
            select(
                func.count(WorkoutEntry.id),
                func.sum(WorkoutEntry.duration),
                func.sum(WorkoutEntry.calories_burned),
            )
            .where(WorkoutEntry.user_id == user_id)
            .where(WorkoutEntry.created_at >= week_ago)
        )
        cnt, dur, burned = result.one()
        return {
            'workout_count': cnt or 0,
            'total_duration': dur or 0,
            'total_burned': burned or 0,
        }


def format_meal_day(day_num: int, items: list, daily_target: int = 2000) -> str:
    """Формирование текста плана питания на день"""
    day_name_full = [
        'Понедельник', 'Вторник', 'Среда', 'Четверг',
        'Пятница', 'Суббота', 'Воскресенье'
    ]
    text = f"🍽 <b>План питания — {day_name_full[day_num]}</b>\n\n"

    total_cal = 0
    total_p = total_f = total_c = 0.0

    for item in items:
        check = "✅" if item.is_completed else "⬜"
        name = MEAL_TYPE_NAMES.get(item.meal_type, '🍽 Приём пищи')
        text += (
            f"{check} <b>{name}</b>\n"
            f"    {item.food_name}\n"
            f"    📊 {item.calories} ккал | "
            f"Б:{item.protein:.0f} Ж:{item.fats:.0f} У:{item.carbs:.0f}\n\n"
        )
        total_cal += item.calories or 0
        total_p += item.protein or 0
        total_f += item.fats or 0
        total_c += item.carbs or 0

    progress = min(100, int((total_cal / daily_target) * 100)) if daily_target else 0
    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

    text += (
        f"<b>Итого за день:</b>\n"
        f"{bar} {total_cal} / {daily_target} ккал\n"
        f"Б:{total_p:.0f}г Ж:{total_f:.0f}г У:{total_c:.0f}г"
    )
    return text


def format_workout_day(day_num: int, item) -> str:
    """Формирование текста плана тренировки на день"""
    day_name_full = [
        'Понедельник', 'Вторник', 'Среда', 'Четверг',
        'Пятница', 'Суббота', 'Воскресенье'
    ]

    if item.is_rest_day:
        check = "✅" if item.is_completed else "😴"
        text = (
            f"🏋️ <b>План тренировок — {day_name_full[day_num]}</b>\n\n"
            f"{check} <b>День отдыха</b>\n\n"
        )
        if item.notes:
            text += f"💡 <i>{item.notes}</i>"
        return text

    check = "✅" if item.is_completed else "💪"
    text = (
        f"🏋️ <b>План тренировок — {day_name_full[day_num]}</b>\n\n"
        f"{check} <b>{item.workout_type}</b>\n"
        f"⏱ {item.duration} мин | 🔥 ~{item.calories_burned} ккал\n\n"
    )

    exercises = item.exercises or []
    if exercises:
        text += "<b>Упражнения:</b>\n"
        for i, ex in enumerate(exercises, 1):
            name = ex.get('name', '?')
            sets = ex.get('sets', '?')
            reps = ex.get('reps', '?')
            rest = ex.get('rest', '')
            text += f"{i}. {name} — {sets}×{reps}"
            if rest:
                text += f" (отдых {rest})"
            text += "\n"
            if ex.get('notes'):
                text += f"   <i>{ex['notes']}</i>\n"

    if item.notes:
        text += f"\n💡 <i>{item.notes}</i>"

    return text


# ==================== План питания ====================

@router.message(F.text == "🍽 План питания")
async def meal_plan_button(message: Message, state: FSMContext):
    """Главная кнопка плана питания"""
    await state.clear()
    user_ctx = await get_user_context(message.from_user.id)
    if not user_ctx.get('daily_target'):
        await message.answer(
            "Сначала настрой профиль командой /start, чтобы AI мог составить план."
        )
        return

    week_start = get_current_week_start()

    async with async_session() as session:
        # Ищем активный план на эту неделю
        plan_result = await session.execute(
            select(MealPlan)
            .where(MealPlan.user_id == message.from_user.id)
            .where(MealPlan.is_active.is_(True))
            .where(MealPlan.week_start == week_start)
        )
        plan = plan_result.scalar_one_or_none()

    if plan:
        # Показываем сегодняшний день
        today = datetime.now().weekday()
        await show_meal_plan_day(message, plan.id, today, user_ctx.get('daily_target', 2000))
    else:
        # Генерируем новый план
        await generate_and_show_meal_plan(message, user_ctx)


async def generate_and_show_meal_plan(message: Message, user_ctx: dict):
    """Генерация и сохранение нового плана питания"""
    await message.answer("🤖 Составляю персональный план питания на неделю...\nЭто может занять до 30 секунд.")

    try:
        recent_stats = await get_recent_food_stats(message.from_user.id)
        ai_plan = await generate_meal_plan(user_ctx, recent_stats)

        week_start = get_current_week_start()

        async with async_session() as session:
            # Деактивируем старые планы
            await session.execute(
                update(MealPlan)
                .where(MealPlan.user_id == message.from_user.id)
                .where(MealPlan.is_active.is_(True))
                .values(is_active=False)
            )

            # Создаём новый план
            plan = MealPlan(
                user_id=message.from_user.id,
                week_start=week_start,
                is_active=True,
                ai_response=ai_plan,
            )
            session.add(plan)
            await session.flush()

            # Сохраняем элементы
            for day_data in ai_plan.get('days', []):
                day_num = day_data.get('day', 0)
                for meal in day_data.get('meals', []):
                    item = MealPlanItem(
                        plan_id=plan.id,
                        user_id=message.from_user.id,
                        day_of_week=day_num,
                        meal_type=meal.get('meal_type', 'snack'),
                        food_name=meal.get('food_name', 'Блюдо'),
                        recipe=meal.get('recipe', ''),
                        ingredients=meal.get('ingredients', ''),
                        calories=meal.get('calories', 0),
                        protein=meal.get('protein', 0),
                        fats=meal.get('fats', 0),
                        carbs=meal.get('carbs', 0),
                    )
                    session.add(item)

            await session.commit()

            # Показываем сегодняшний день
            today = datetime.now().weekday()
            await show_meal_plan_day(
                message, plan.id, today,
                user_ctx.get('daily_target', 2000)
            )

    except Exception as e:
        logger.exception("Ошибка генерации плана питания")
        await message.answer(
            "❌ Не удалось сгенерировать план питания.\n\nПопробуй ещё раз позже."
        )


async def show_meal_plan_day(target, plan_id: int, day: int, daily_target: int = 2000):
    """Показать день плана питания (target — Message или CallbackQuery)"""
    async with async_session() as session:
        result = await session.execute(
            select(MealPlanItem)
            .where(MealPlanItem.plan_id == plan_id)
            .where(MealPlanItem.day_of_week == day)
            .order_by(MealPlanItem.id)
        )
        items = result.scalars().all()

    if not items:
        text = f"🍽 <b>План питания — {DAY_NAMES[day]}</b>\n\nНет данных на этот день."
        kb = get_meal_plan_day_keyboard(plan_id, day, [])
    else:
        text = format_meal_day(day, items, daily_target)
        kb = get_meal_plan_day_keyboard(plan_id, day, items)

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


# ==================== План тренировок ====================

@router.message(F.text == "🏋️ План тренировок")
async def workout_plan_button(message: Message, state: FSMContext):
    """Главная кнопка плана тренировок"""
    await state.clear()
    user_ctx = await get_user_context(message.from_user.id)
    if not user_ctx.get('daily_target'):
        await message.answer(
            "Сначала настрой профиль командой /start, чтобы AI мог составить план."
        )
        return

    week_start = get_current_week_start()

    async with async_session() as session:
        plan_result = await session.execute(
            select(WorkoutPlan)
            .where(WorkoutPlan.user_id == message.from_user.id)
            .where(WorkoutPlan.is_active.is_(True))
            .where(WorkoutPlan.week_start == week_start)
        )
        plan = plan_result.scalar_one_or_none()

    if plan:
        today = datetime.now().weekday()
        await show_workout_plan_day(message, plan.id, today)
    else:
        await generate_and_show_workout_plan(message, user_ctx)


async def generate_and_show_workout_plan(message: Message, user_ctx: dict):
    """Генерация и сохранение нового плана тренировок"""
    await message.answer("🤖 Составляю персональный план тренировок на неделю...\nЭто может занять до 30 секунд.")

    try:
        recent_stats = await get_recent_workout_stats(message.from_user.id)
        ai_plan = await generate_workout_plan(user_ctx, recent_stats)

        week_start = get_current_week_start()

        async with async_session() as session:
            await session.execute(
                update(WorkoutPlan)
                .where(WorkoutPlan.user_id == message.from_user.id)
                .where(WorkoutPlan.is_active.is_(True))
                .values(is_active=False)
            )

            plan = WorkoutPlan(
                user_id=message.from_user.id,
                week_start=week_start,
                is_active=True,
                ai_response=ai_plan,
            )
            session.add(plan)
            await session.flush()

            for day_data in ai_plan.get('days', []):
                day_num = day_data.get('day', 0)
                item = WorkoutPlanItem(
                    plan_id=plan.id,
                    user_id=message.from_user.id,
                    day_of_week=day_num,
                    workout_type=day_data.get('workout_type', 'Тренировка'),
                    exercises=day_data.get('exercises', []),
                    duration=day_data.get('duration', 0),
                    calories_burned=day_data.get('calories_burned', 0),
                    notes=day_data.get('notes', ''),
                    is_rest_day=day_data.get('is_rest_day', False),
                )
                session.add(item)

            await session.commit()

            today = datetime.now().weekday()
            await show_workout_plan_day(message, plan.id, today)

    except Exception as e:
        logger.exception("Ошибка генерации плана тренировок")
        await message.answer(
            "❌ Не удалось сгенерировать план тренировок.\n\nПопробуй ещё раз позже."
        )


async def show_workout_plan_day(target, plan_id: int, day: int):
    """Показать день плана тренировок"""
    async with async_session() as session:
        result = await session.execute(
            select(WorkoutPlanItem)
            .where(WorkoutPlanItem.plan_id == plan_id)
            .where(WorkoutPlanItem.day_of_week == day)
        )
        item = result.scalar_one_or_none()

    if not item:
        text = f"🏋️ <b>План тренировок — {DAY_NAMES[day]}</b>\n\nНет данных на этот день."
        kb = get_workout_plan_day_keyboard(plan_id, day)
    else:
        text = format_workout_day(day, item)
        kb = get_workout_plan_day_keyboard(plan_id, day, item)

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


# ==================== Навигация по дням ====================

@router.callback_query(F.data.startswith("mpd_"))
async def navigate_meal_plan_day(callback: CallbackQuery):
    """Переключение дня в плане питания"""
    parts = callback.data.split("_")
    plan_id = int(parts[1])
    day = int(parts[2])

    # Проверка владельца плана
    async with async_session() as session:
        result = await session.execute(
            select(MealPlan).where(MealPlan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if not plan or plan.user_id != callback.from_user.id:
            await callback.answer("Доступ запрещён")
            return

    user_ctx = await get_user_context(callback.from_user.id)
    daily_target = user_ctx.get('daily_target', 2000)

    await show_meal_plan_day(callback, plan_id, day, daily_target)
    await callback.answer()


@router.callback_query(F.data.startswith("wpd_"))
async def navigate_workout_plan_day(callback: CallbackQuery):
    """Переключение дня в плане тренировок"""
    parts = callback.data.split("_")
    plan_id = int(parts[1])
    day = int(parts[2])

    # Проверка владельца плана
    async with async_session() as session:
        result = await session.execute(
            select(WorkoutPlan).where(WorkoutPlan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if not plan or plan.user_id != callback.from_user.id:
            await callback.answer("Доступ запрещён")
            return

    await show_workout_plan_day(callback, plan_id, day)
    await callback.answer()


# ==================== Отметка выполнения ====================

@router.callback_query(F.data.startswith("mpc_"))
async def complete_meal_item(callback: CallbackQuery):
    """Отметить приём пищи как выполненный + записать в calorie_entries"""
    item_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(MealPlanItem).where(MealPlanItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item or item.user_id != callback.from_user.id:
            await callback.answer("Доступ запрещён")
            return
        if item.is_completed:
            await callback.answer("Уже отмечено!")
            return

        # Отмечаем выполненным
        item.is_completed = True
        item.completed_at = datetime.now()

        # Автоматически записываем в дневник калорий
        entry = CalorieEntry(
            user_id=item.user_id,
            food_name=item.food_name,
            calories=item.calories or 0,
            protein=item.protein or 0,
            carbs=item.carbs or 0,
            fats=item.fats or 0,
            meal_type=item.meal_type,
            source_type='meal_plan',
        )
        session.add(entry)
        await session.commit()

        plan_id = item.plan_id
        day = item.day_of_week

    # Обновляем отображение дня
    user_ctx = await get_user_context(callback.from_user.id)
    daily_target = user_ctx.get('daily_target', 2000)
    await show_meal_plan_day(callback, plan_id, day, daily_target)
    await callback.answer("✅ Записано в дневник!")


@router.callback_query(F.data.startswith("wpc_"))
async def complete_workout_item(callback: CallbackQuery):
    """Отметить тренировку как выполненную + записать в workout_entries"""
    item_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(WorkoutPlanItem).where(WorkoutPlanItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item or item.user_id != callback.from_user.id:
            await callback.answer("Доступ запрещён")
            return
        if item.is_completed:
            await callback.answer("Уже отмечено!")
            return

        item.is_completed = True
        item.completed_at = datetime.now()

        # Автоматически записываем в дневник тренировок
        entry = WorkoutEntry(
            user_id=item.user_id,
            workout_type=item.workout_type,
            duration=item.duration or 0,
            calories_burned=item.calories_burned or 0,
            notes=f"Из плана тренировок",
            source_type='workout_plan',
        )
        session.add(entry)
        await session.commit()

        plan_id = item.plan_id
        day = item.day_of_week

    await show_workout_plan_day(callback, plan_id, day)
    await callback.answer("✅ Тренировка записана!")


# ==================== Рецепт ====================

@router.callback_query(F.data.startswith("mpr_"))
async def show_recipe(callback: CallbackQuery):
    """Показать рецепт блюда из плана"""
    item_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(MealPlanItem).where(MealPlanItem.id == item_id)
        )
        item = result.scalar_one_or_none()

    if not item or item.user_id != callback.from_user.id:
        await callback.answer("Доступ запрещён")
        return

    meal_name = MEAL_TYPE_NAMES.get(item.meal_type, '🍽 Приём пищи')

    text = (
        f"📖 <b>{meal_name}: {item.food_name}</b>\n\n"
        f"📊 {item.calories} ккал | "
        f"Б:{item.protein:.0f}г Ж:{item.fats:.0f}г У:{item.carbs:.0f}г\n\n"
    )

    if item.ingredients:
        text += f"<b>Ингредиенты:</b>\n{item.ingredients}\n\n"

    if item.recipe:
        text += f"<b>Приготовление:</b>\n{item.recipe}"

    # Отправляем отдельным сообщением (чтобы не потерять навигацию)
    await callback.message.answer(text)
    await callback.answer()


# ==================== Генерация нового плана ====================

@router.callback_query(F.data == "mpn")
async def new_meal_plan(callback: CallbackQuery):
    """Сгенерировать новый план питания"""
    user_ctx = await get_user_context(callback.from_user.id)
    if not user_ctx.get('daily_target'):
        await callback.answer("Сначала настрой профиль!")
        return

    await callback.answer("Генерирую новый план...")
    await generate_and_show_meal_plan(callback.message, user_ctx)


@router.callback_query(F.data == "wpn")
async def new_workout_plan(callback: CallbackQuery):
    """Сгенерировать новый план тренировок"""
    user_ctx = await get_user_context(callback.from_user.id)
    if not user_ctx.get('daily_target'):
        await callback.answer("Сначала настрой профиль!")
        return

    await callback.answer("Генерирую новый план...")
    await generate_and_show_workout_plan(callback.message, user_ctx)


# ==================== Noop ====================

@router.callback_query(F.data == "_")
async def noop_callback(callback: CallbackQuery):
    """Заглушка для неактивных кнопок"""
    await callback.answer()
