"""
AI Hub - Единый обработчик всех типов сообщений (голос, фото, текст)
с подтверждением перед сохранением
"""
from aiogram import Router, F
from aiogram.types import Message, Voice, PhotoSize, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from datetime import datetime, timedelta
import os

from database.database import (
    async_session, User, CalorieEntry, WorkoutEntry, AIInteraction, calc_today_start
)
from keyboards.reply import (
    get_main_menu, MENU_BUTTONS, not_menu_button,
    get_ai_food_confirm_keyboard, get_ai_workout_confirm_keyboard
)
from utils.openai_helper import (
    transcribe_voice,
    analyze_food_from_text,
    analyze_food_from_photo,
    analyze_workout_from_text,
    get_smart_recommendation
)

router = Router()

# Директория для хранения медиа-файлов
MEDIA_DIR = "/app/media"
os.makedirs(f"{MEDIA_DIR}/voice", exist_ok=True)
os.makedirs(f"{MEDIA_DIR}/photos", exist_ok=True)


class AIInput(StatesGroup):
    """Состояния для AI-ввода"""
    waiting_for_food_edit = State()
    waiting_for_workout_edit = State()
    waiting_for_workout_duration = State()


# ==================== Вспомогательные функции ====================

async def get_user_context(user_id: int) -> dict:
    """Получение контекста пользователя для AI"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return {
                'age': user.age,
                'gender': user.gender,
                'weight': user.weight,
                'height': user.height,
                'goal': user.goal,
                'activity_level': user.activity_level,
                'daily_target': user.daily_calorie_target
            }
        return {}


async def show_food_confirmation(message: Message, state: FSMContext,
                                  food_data: dict, source_type: str,
                                  file_path: str = None, original_text: str = None):
    """Показать распознанную еду с кнопками подтверждения"""
    await state.update_data(
        pending_food=food_data,
        pending_food_source_type=source_type,
        pending_food_file_path=file_path,
        pending_food_text=original_text
    )
    await state.set_state(None)

    confidence_emoji = "✅" if food_data.get('confidence', 0) > 0.8 else "⚠️"

    response = (
        f"{confidence_emoji} <b>AI распознал:</b>\n\n"
        f"🍽 <b>{food_data['food_name']}</b>\n"
        f"📊 Калории: <b>{food_data['calories']} ккал</b>\n"
        f"Б/Ж/У: {food_data.get('protein', 0):.1f} / "
        f"{food_data.get('fats', 0):.1f} / "
        f"{food_data.get('carbs', 0):.1f} г\n"
    )

    if food_data.get('items'):
        items_text = "\n".join([f"  • {item}" for item in food_data['items']])
        response += f"\n<b>Состав:</b>\n{items_text}\n"

    if food_data.get('notes'):
        notes = food_data['notes'].replace('<', '&lt;').replace('>', '&gt;')
        response += f"\n💡 <i>{notes}</i>"

    await message.answer(response, reply_markup=get_ai_food_confirm_keyboard())


async def show_workout_confirmation(message: Message, state: FSMContext,
                                     workout_data: dict, source_type: str,
                                     original_text: str = None):
    """Показать распознанную тренировку с кнопками подтверждения"""
    await state.update_data(
        pending_workout=workout_data,
        pending_workout_source_type=source_type,
        pending_workout_text=original_text
    )
    await state.set_state(None)

    intensity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}

    response = (
        f"🤖 <b>AI распознал:</b>\n\n"
        f"🏃 <b>{workout_data['workout_type']}</b>\n"
        f"⏱ Длительность: <b>{workout_data['duration']}</b> мин\n"
        f"🔥 Сожжено: <b>~{workout_data.get('calories_burned', 0)}</b> ккал\n"
        f"{intensity_emoji.get(workout_data.get('intensity', 'medium'), '⚪')} "
        f"Интенсивность: {workout_data.get('intensity', 'средняя')}\n"
    )

    if workout_data.get('distance'):
        response += f"📏 Дистанция: {workout_data['distance']} км\n"
    if workout_data.get('pace'):
        response += f"⚡️ Темп: {workout_data['pace']}\n"
    if workout_data.get('notes'):
        response += f"\n💡 <i>{workout_data['notes']}</i>"

    await message.answer(response, reply_markup=get_ai_workout_confirm_keyboard())


async def analyze_and_show_food(message: Message, state: FSMContext,
                                 text: str, source_type: str, file_path: str = None):
    """Анализ еды через AI и показ подтверждения"""
    try:
        user_context = await get_user_context(message.from_user.id)
        food_data = await analyze_food_from_text(text, user_context)
        await show_food_confirmation(message, state, food_data, source_type, file_path, text)
    except Exception as e:
        await message.answer(f"❌ Ошибка анализа: {str(e)}")


async def analyze_and_show_workout(message: Message, state: FSMContext,
                                    text: str, source_type: str):
    """Анализ тренировки через AI и показ подтверждения (или запрос длительности)"""
    try:
        workout_data = await analyze_workout_from_text(text)

        if not workout_data.get('duration') or workout_data['duration'] == 0:
            # Нужно уточнить длительность
            await state.update_data(
                pending_workout=workout_data,
                pending_workout_source_type=source_type,
                pending_workout_text=text
            )
            workout_name = workout_data.get('workout_type', 'Тренировка')
            await message.answer(
                f"🤖 Распознал: <b>{workout_name}</b>\n\n"
                "Сколько минут длилась тренировка? (введи число)"
            )
            await state.set_state(AIInput.waiting_for_workout_duration)
        else:
            await show_workout_confirmation(message, state, workout_data, source_type, text)
    except Exception as e:
        await message.answer(f"❌ Ошибка анализа: {str(e)}")


async def save_food_to_db(user_id: int, food_data: dict, source_type: str,
                           file_path: str = None, original_text: str = None) -> int:
    """Сохранение еды в БД"""
    async with async_session() as session:
        entry = CalorieEntry(
            user_id=user_id,
            food_name=food_data['food_name'],
            calories=food_data['calories'],
            protein=food_data.get('protein', 0),
            carbs=food_data.get('carbs', 0),
            fats=food_data.get('fats', 0),
            meal_type=food_data.get('meal_type', 'snack'),
            source_type=source_type,
            source_data={'original_text': original_text, 'file_path': file_path},
            ai_confidence=food_data.get('confidence', 0),
            ai_notes=food_data.get('notes', '')
        )
        session.add(entry)
        await session.flush()

        ai_log = AIInteraction(
            user_id=user_id,
            interaction_type='food_analysis',
            input_type=source_type,
            input_data=original_text,
            input_file_path=file_path,
            ai_response=food_data,
            ai_model='gpt-4o-mini',
            ai_confidence=food_data.get('confidence', 0),
            created_entry_type='calorie_entry',
            created_entry_id=entry.id
        )
        session.add(ai_log)
        await session.commit()
        return entry.id


async def save_workout_to_db(user_id: int, workout_data: dict,
                              source_type: str, original_text: str = None) -> int:
    """Сохранение тренировки в БД"""
    async with async_session() as session:
        entry = WorkoutEntry(
            user_id=user_id,
            workout_type=workout_data['workout_type'],
            duration=workout_data['duration'],
            calories_burned=workout_data.get('calories_burned', 0),
            notes=workout_data.get('notes', ''),
            source_type=source_type,
            intensity=workout_data.get('intensity'),
            distance=workout_data.get('distance'),
            pace=workout_data.get('pace'),
            ai_confidence=workout_data.get('confidence', 0)
        )
        session.add(entry)
        await session.flush()

        ai_log = AIInteraction(
            user_id=user_id,
            interaction_type='workout_analysis',
            input_type=source_type,
            input_data=original_text,
            ai_response=workout_data,
            ai_model='gpt-4o-mini',
            ai_confidence=workout_data.get('confidence', 0),
            created_entry_type='workout_entry',
            created_entry_id=entry.id
        )
        session.add(ai_log)
        await session.commit()
        return entry.id


async def process_consultation(message: Message, query: str):
    """Обработка консультационного запроса"""
    try:
        user_context = await get_user_context(message.from_user.id)
        recommendation = await get_smart_recommendation(user_context, query)

        async with async_session() as session:
            ai_log = AIInteraction(
                user_id=message.from_user.id,
                interaction_type='consultation',
                input_type='text',
                input_data=query,
                ai_response={'recommendation': recommendation},
                ai_model='gpt-4o'
            )
            session.add(ai_log)
            await session.commit()

        await message.answer(
            f"🤖 <b>Персональная рекомендация:</b>\n\n{recommendation}",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ==================== Кнопка «Быстрый ввод» ====================

@router.message(F.text == "✨ Быстрый ввод")
async def quick_input(message: Message, state: FSMContext):
    """Инструкция по AI-вводу"""
    await state.clear()
    await message.answer(
        "✨ <b>Быстрый ввод с помощью AI</b>\n\n"
        "Просто отправь мне информацию в любом формате:\n\n"
        "🍽 <b>Еда:</b>\n"
        '• Текст: <i>"Съел борщ с хлебом и котлету"</i>\n'
        "• Фото: сфотографируй тарелку с едой\n"
        "• Голосовое: надиктуй что съел\n\n"
        "🏃 <b>Тренировка:</b>\n"
        '• Текст: <i>"Пробежал 5 км за 30 минут"</i>\n'
        "• Голосовое: расскажи о тренировке\n\n"
        "❓ <b>Вопрос:</b>\n"
        '• <i>"Что мне съесть на ужин?"</i>\n'
        '• <i>"Посоветуй тренировку"</i>\n\n'
        "AI проанализирует и предложит добавить запись.\n"
        "Ты сможешь <b>подтвердить</b> или <b>изменить</b> данные перед сохранением."
    )


# ==================== Голосовые сообщения ====================

@router.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    """Обработка голосовых сообщений"""
    await state.clear()
    await message.answer("🎤 Слушаю... Обрабатываю голосовое сообщение...")

    file_path = None
    try:
        voice: Voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_path = f"{MEDIA_DIR}/voice/{message.from_user.id}_{datetime.now().timestamp()}.ogg"
        await message.bot.download_file(file.file_path, file_path)

        transcribed_text = await transcribe_voice(file_path)

        if any(word in transcribed_text.lower() for word in
               ['съел', 'поел', 'завтрак', 'обед', 'ужин', 'калори', 'еда', 'блюдо']):
            await analyze_and_show_food(message, state, transcribed_text, 'voice', file_path)
        elif any(word in transcribed_text.lower() for word in
                 ['тренировка', 'пробежал', 'зал', 'качалка', 'бег', 'плавал', 'йога']):
            await analyze_and_show_workout(message, state, transcribed_text, 'voice')
        else:
            await process_consultation(message, transcribed_text)

    except Exception as e:
        await message.answer(
            f"❌ Ошибка обработки голосового сообщения: {str(e)}\n\n"
            "Попробуйте еще раз или используйте текст."
        )
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


# ==================== Фото ====================

@router.message(F.photo)
async def handle_photo_message(message: Message, state: FSMContext):
    """Обработка фотографий (еда) — с подтверждением"""
    await state.clear()
    await message.answer("📸 Анализирую фото... Это может занять несколько секунд...")

    file_path = None
    try:
        photo: PhotoSize = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_path = f"{MEDIA_DIR}/photos/{message.from_user.id}_{datetime.now().timestamp()}.jpg"
        await message.bot.download_file(file.file_path, file_path)

        user_context = await get_user_context(message.from_user.id)
        food_data = await analyze_food_from_photo(file_path, user_context)

        await show_food_confirmation(message, state, food_data, 'photo', file_path)

    except Exception as e:
        await message.answer(
            f"❌ Ошибка анализа фото: {str(e)}\n\n"
            "Попробуйте сфотографировать еду с другого ракурса."
        )
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


# ==================== FSM-хэндлеры (до catch-all) ====================

@router.message(AIInput.waiting_for_food_edit, not_menu_button)
async def process_food_edit(message: Message, state: FSMContext):
    """Повторный анализ еды после редактирования"""
    await message.answer("🤖 Анализирую заново...")
    data = await state.get_data()
    source_type = data.get('pending_food_source_type', 'text_ai')
    file_path = data.get('pending_food_file_path')
    await analyze_and_show_food(message, state, message.text.strip(), source_type, file_path)


@router.message(AIInput.waiting_for_workout_edit, not_menu_button)
async def process_workout_edit(message: Message, state: FSMContext):
    """Повторный анализ тренировки после редактирования"""
    await message.answer("🤖 Анализирую заново...")
    data = await state.get_data()
    source_type = data.get('pending_workout_source_type', 'text_ai')
    await analyze_and_show_workout(message, state, message.text.strip(), source_type)


@router.message(AIInput.waiting_for_workout_duration, not_menu_button)
async def process_workout_duration_input(message: Message, state: FSMContext):
    """Ввод длительности тренировки, если AI не смог определить"""
    try:
        duration = int(message.text)
        if duration < 1 or duration > 600:
            await message.answer("Введи длительность от 1 до 600 минут:")
            return

        data = await state.get_data()
        workout_data = data['pending_workout']
        workout_data['duration'] = duration
        if not workout_data.get('calories_burned'):
            workout_data['calories_burned'] = int(duration * 5)

        source_type = data.get('pending_workout_source_type', 'text_ai')
        original_text = data.get('pending_workout_text')
        await show_workout_confirmation(message, state, workout_data, source_type, original_text)
    except (ValueError, KeyError):
        await message.answer("Пожалуйста, введи длительность числом:")


# ==================== Callback-хэндлеры подтверждения ====================

@router.callback_query(F.data == "ai_food_confirm")
async def confirm_food(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение еды"""
    data = await state.get_data()
    food_data = data.get('pending_food')
    if not food_data:
        await callback.answer("Данные устарели, попробуй заново")
        return

    await save_food_to_db(
        callback.from_user.id, food_data,
        data.get('pending_food_source_type', 'text_ai'),
        data.get('pending_food_file_path'),
        data.get('pending_food_text')
    )

    # Статистика за сегодня
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        target = user.daily_calorie_target or 2000 if user else 2000
        today_start = calc_today_start(user.current_day_start if user else None)

        result = await session.execute(
            select(func.sum(CalorieEntry.calories))
            .where(CalorieEntry.user_id == callback.from_user.id)
            .where(CalorieEntry.created_at >= today_start)
        )
        total_today = result.scalar() or 0

    remaining = target - total_today
    progress_percent = min(100, int((total_today / target) * 100))
    progress_bar = "█" * (progress_percent // 10) + "░" * (10 - progress_percent // 10)

    await callback.message.edit_text(
        f"✅ <b>Добавлено!</b>\n\n"
        f"🍽 <b>{food_data['food_name']}</b>: <b>{food_data['calories']} ккал</b>\n\n"
        f"📊 <b>За сегодня:</b>\n"
        f"{progress_bar} {progress_percent}%\n"
        f"Съедено: <b>{total_today}</b> / {target} ккал\n"
        f"Осталось: <b>{remaining}</b> ккал"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "ai_food_edit")
async def edit_food(callback: CallbackQuery, state: FSMContext):
    """Редактирование распознанной еды"""
    await callback.message.edit_text(
        "Опиши заново что ты ел(а), или уточни детали:\n\n"
        'Например: <i>"Это была большая порция"</i> или <i>"Борщ и 2 котлеты"</i>'
    )
    await state.set_state(AIInput.waiting_for_food_edit)
    await callback.answer()


@router.callback_query(F.data == "ai_workout_confirm")
async def confirm_workout(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение тренировки"""
    data = await state.get_data()
    workout_data = data.get('pending_workout')
    if not workout_data:
        await callback.answer("Данные устарели, попробуй заново")
        return

    await save_workout_to_db(
        callback.from_user.id, workout_data,
        data.get('pending_workout_source_type', 'text_ai'),
        data.get('pending_workout_text')
    )

    # Статистика за неделю
    week_ago = datetime.now() - timedelta(days=7)
    async with async_session() as session:
        result = await session.execute(
            select(
                func.count(WorkoutEntry.id),
                func.sum(WorkoutEntry.duration),
                func.sum(WorkoutEntry.calories_burned)
            )
            .where(WorkoutEntry.user_id == callback.from_user.id)
            .where(WorkoutEntry.created_at >= week_ago)
        )
        week_count, week_duration, week_calories = result.one()

    await callback.message.edit_text(
        f"✅ <b>Тренировка добавлена!</b>\n\n"
        f"🏃 <b>{workout_data['workout_type']}</b>\n"
        f"⏱ {workout_data['duration']} мин | "
        f"🔥 ~{workout_data.get('calories_burned', 0)} ккал\n\n"
        f"📊 <b>За последние 7 дней:</b>\n"
        f"Тренировок: <b>{week_count or 0}</b>\n"
        f"Время: <b>{week_duration or 0}</b> мин\n"
        f"Сожжено: <b>~{week_calories or 0}</b> ккал"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "ai_workout_edit")
async def edit_workout(callback: CallbackQuery, state: FSMContext):
    """Редактирование распознанной тренировки"""
    await callback.message.edit_text(
        "Опиши заново свою тренировку:\n\n"
        'Например: <i>"Бег 30 минут, 5 км"</i>'
    )
    await state.set_state(AIInput.waiting_for_workout_edit)
    await callback.answer()


# ==================== Catch-all текстовый хэндлер (последний) ====================

@router.message(F.text & ~F.text.startswith('/') & ~F.text.in_(MENU_BUTTONS))
async def handle_text_message(message: Message, state: FSMContext):
    """Обработка текстовых сообщений (умный анализ)"""
    text = message.text.strip()

    if any(word in text.lower() for word in
           ['съел', 'поел', 'завтрак', 'обед', 'ужин', 'калори', 'еда']):
        await message.answer("🤖 Анализирую питание...")
        await analyze_and_show_food(message, state, text, 'text_ai')

    elif any(word in text.lower() for word in
             ['тренировка', 'пробежал', 'зал', 'бег', 'плавал', 'йога', 'км',
              'минут тренировался']):
        await message.answer("🤖 Анализирую тренировку...")
        await analyze_and_show_workout(message, state, text, 'text_ai')

    elif any(word in text.lower() for word in
             ['что', 'как', 'посоветуй', 'рекомендуй', 'помоги', 'скажи']):
        await message.answer("🤔 Анализирую твои данные и готовлю рекомендацию...")
        await process_consultation(message, text)
    else:
        await message.answer(
            "Я не совсем понял. Попробуй:\n"
            '• Опиши что ел: <i>"Съел борщ и котлету"</i>\n'
            '• Расскажи о тренировке: <i>"Пробежал 5км за 30 минут"</i>\n'
            '• Задай вопрос: <i>"Что мне съесть на ужин?"</i>\n'
            "• Или отправь фото еды 📸"
        )
