from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from datetime import datetime, timedelta

from database.database import async_session, WorkoutEntry
from keyboards.reply import get_workout_type_keyboard, get_main_menu, not_menu_button

router = Router()


class AddWorkout(StatesGroup):
    """Состояния для добавления тренировки"""
    waiting_for_workout_type = State()
    waiting_for_duration = State()
    waiting_for_notes = State()


# Примерные калории, сжигаемые за 30 минут тренировки (для человека весом 70 кг)
CALORIES_PER_30MIN = {
    'running': 300,
    'gym': 200,
    'cycling': 250,
    'yoga': 120,
    'swimming': 250,
    'other': 150
}


@router.message(F.text == "🏃 Добавить тренировку")
async def start_add_workout(message: Message, state: FSMContext):
    """Начало процесса добавления тренировки"""
    await state.clear()
    await message.answer(
        "Какой тип тренировки?",
        reply_markup=get_workout_type_keyboard()
    )
    await state.set_state(AddWorkout.waiting_for_workout_type)


@router.callback_query(F.data.startswith("workout_"))
async def process_workout_type(callback: CallbackQuery, state: FSMContext):
    """Обработка типа тренировки"""
    workout_type = callback.data.split("_")[1]

    if workout_type == "other":
        await callback.message.edit_text(
            "Напиши название тренировки:"
        )
        await state.update_data(workout_type="other", custom_name=True)
    else:
        workout_names = {
            'running': 'Бег',
            'gym': 'Тренажерный зал',
            'cycling': 'Велосипед',
            'yoga': 'Йога',
            'swimming': 'Плавание'
        }
        await state.update_data(workout_type=workout_type, workout_name=workout_names[workout_type])
        await callback.message.edit_text(
            f"Отлично! <b>{workout_names[workout_type]}</b>\n\n"
            "Сколько минут тренировался? (введи число)"
        )

    await state.set_state(AddWorkout.waiting_for_duration)
    await callback.answer()


@router.message(AddWorkout.waiting_for_duration, not_menu_button)
async def process_duration(message: Message, state: FSMContext):
    """Обработка продолжительности тренировки"""
    data = await state.get_data()

    # Если это кастомная тренировка и мы еще не получили название
    if data.get('custom_name') and 'workout_name' not in data:
        await state.update_data(workout_name=message.text.strip())
        await message.answer("Сколько минут тренировался? (введи число)")
        return

    try:
        duration = int(message.text)
        if duration < 1 or duration > 600:
            await message.answer("Пожалуйста, введи корректную длительность (от 1 до 600 минут)")
            return

        # Рассчитываем примерное количество сожженных калорий
        workout_type = data['workout_type']
        calories_per_30 = CALORIES_PER_30MIN.get(workout_type, 150)
        calories_burned = int((duration / 30) * calories_per_30)

        await state.update_data(duration=duration, calories_burned=calories_burned)
        await message.answer(
            f"Хочешь добавить заметки о тренировке?\n\n"
            f"Например: <i>Хорошее самочувствие, новый рекорд</i>\n\n"
            "Или отправь <b>-</b> чтобы пропустить"
        )
        await state.set_state(AddWorkout.waiting_for_notes)
    except ValueError:
        await message.answer("Пожалуйста, введи длительность числом")


@router.message(AddWorkout.waiting_for_notes, not_menu_button)
async def process_notes(message: Message, state: FSMContext):
    """Сохранение тренировки"""
    data = await state.get_data()
    notes = None if message.text.strip() == "-" else message.text.strip()

    # Сохраняем в БД
    async with async_session() as session:
        entry = WorkoutEntry(
            user_id=message.from_user.id,
            workout_type=data['workout_name'],
            duration=data['duration'],
            calories_burned=data['calories_burned'],
            notes=notes
        )
        session.add(entry)
        await session.commit()

        # Получаем статистику за неделю
        week_ago = datetime.now() - timedelta(days=7)
        result = await session.execute(
            select(
                func.count(WorkoutEntry.id),
                func.sum(WorkoutEntry.duration),
                func.sum(WorkoutEntry.calories_burned)
            )
            .where(WorkoutEntry.user_id == message.from_user.id)
            .where(WorkoutEntry.created_at >= week_ago)
        )
        week_count, week_duration, week_calories = result.one()
        week_count = week_count or 0
        week_duration = week_duration or 0
        week_calories = week_calories or 0

    response = (
        f"✅ Тренировка добавлена!\n\n"
        f"🏃 <b>{data['workout_name']}</b>\n"
        f"⏱ Длительность: <b>{data['duration']}</b> мин\n"
        f"🔥 Сожжено калорий: <b>~{data['calories_burned']}</b> ккал\n"
    )

    if notes:
        response += f"📝 Заметки: <i>{notes}</i>\n"

    response += (
        f"\n📊 <b>За последние 7 дней:</b>\n"
        f"Тренировок: <b>{week_count}</b>\n"
        f"Время: <b>{week_duration}</b> мин\n"
        f"Сожжено: <b>~{week_calories}</b> ккал"
    )

    await message.answer(response, reply_markup=get_main_menu())
    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel_workout_action(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления тренировки"""
    await callback.message.edit_text("❌ Добавление отменено")
    await state.clear()
    await callback.answer()
