from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from datetime import datetime, timedelta

from database.database import async_session, CalorieEntry, User, calc_today_start
from keyboards.reply import get_meal_type_keyboard, get_main_menu, not_menu_button

router = Router()


class AddCalories(StatesGroup):
    """Состояния для добавления калорий"""
    waiting_for_food_name = State()
    waiting_for_calories = State()
    waiting_for_meal_type = State()



@router.message(AddCalories.waiting_for_food_name, not_menu_button)
async def process_food_name(message: Message, state: FSMContext):
    """Обработка названия еды"""
    food_name = message.text.strip()

    if len(food_name) < 2:
        await message.answer("Название слишком короткое. Попробуй еще раз:")
        return

    await state.update_data(food_name=food_name)
    await message.answer(
        f"Отлично! <b>{food_name}</b>\n\n"
        "Теперь введи количество калорий (число):"
    )
    await state.set_state(AddCalories.waiting_for_calories)


@router.message(AddCalories.waiting_for_calories, not_menu_button)
async def process_calories(message: Message, state: FSMContext):
    """Обработка калорий"""
    try:
        calories = int(message.text)
        if calories < 1 or calories > 10000:
            await message.answer("Пожалуйста, введи корректное количество калорий (от 1 до 10000)")
            return

        await state.update_data(calories=calories)
        await message.answer(
            "К какому приему пищи отнести?",
            reply_markup=get_meal_type_keyboard()
        )
        await state.set_state(AddCalories.waiting_for_meal_type)
    except ValueError:
        await message.answer("Пожалуйста, введи калории числом")


@router.callback_query(F.data.startswith("meal_"))
async def process_meal_type(callback: CallbackQuery, state: FSMContext):
    """Сохранение записи о калориях"""
    meal_type = callback.data.split("_")[1]
    data = await state.get_data()

    # Сохраняем в БД
    async with async_session() as session:
        entry = CalorieEntry(
            user_id=callback.from_user.id,
            food_name=data['food_name'],
            calories=data['calories'],
            meal_type=meal_type
        )
        session.add(entry)
        await session.commit()

        # Получаем данные пользователя для /new_day и целевой калорийности
        user_result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        today_start = calc_today_start(user.current_day_start if user else None)
        target = user.daily_calorie_target if user and user.daily_calorie_target else 2000

        # Получаем статистику за сегодня
        result = await session.execute(
            select(func.sum(CalorieEntry.calories))
            .where(CalorieEntry.user_id == callback.from_user.id)
            .where(CalorieEntry.created_at >= today_start)
        )
        total_today = result.scalar() or 0

    meal_emoji = {
        'breakfast': '🌅',
        'lunch': '🌞',
        'dinner': '🌙',
        'snack': '🍎'
    }

    remaining = target - total_today
    progress_percent = min(100, int((total_today / target) * 100))
    progress_bar = "█" * (progress_percent // 10) + "░" * (10 - progress_percent // 10)

    await callback.message.edit_text(
        f"✅ Добавлено!\n\n"
        f"{meal_emoji.get(meal_type, '🍽')} <b>{data['food_name']}</b>\n"
        f"Калории: <b>{data['calories']} ккал</b>\n\n"
        f"📊 <b>За сегодня:</b>\n"
        f"{progress_bar} {progress_percent}%\n"
        f"Съедено: <b>{total_today}</b> / {target} ккал\n"
        f"Осталось: <b>{remaining}</b> ккал"
    )

    await callback.message.answer(
        "Что дальше?",
        reply_markup=get_main_menu()
    )

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    await callback.message.edit_text("❌ Действие отменено")
    await state.clear()
    await callback.answer()
