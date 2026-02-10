"""
AI Hub - Единый обработчик всех типов сообщений (голос, фото, текст)
"""
from aiogram import Router, F
from aiogram.types import Message, Voice, PhotoSize
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from datetime import datetime
import os
import aiofiles

from database.database import async_session, User, CalorieEntry, WorkoutEntry, AIInteraction
from keyboards.reply import get_main_menu
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


@router.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    """Обработка голосовых сообщений"""
    await message.answer("🎤 Слушаю... Обрабатываю голосовое сообщение...")
    
    try:
        # Скачиваем голосовое сообщение
        voice: Voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_path = f"{MEDIA_DIR}/voice/{message.from_user.id}_{datetime.now().timestamp()}.ogg"
        
        await message.bot.download_file(file.file_path, file_path)
        
        # Транскрибируем в текст
        transcribed_text = await transcribe_voice(file_path)
        
        # Определяем тип сообщения (еда или тренировка)
        if any(word in transcribed_text.lower() for word in ['съел', 'поел', 'завтрак', 'обед', 'ужин', 'калори', 'еда', 'блюдо']):
            # Это о еде
            await process_food_entry(message, transcribed_text, 'voice', file_path)
        elif any(word in transcribed_text.lower() for word in ['тренировка', 'пробежал', 'зал', 'качалка', 'бег', 'плавал', 'йога']):
            # Это о тренировке
            await process_workout_entry(message, transcribed_text, 'voice')
        else:
            # Общий запрос - используем консультацию AI
            await process_consultation(message, transcribed_text)
            
    except Exception as e:
        await message.answer(
            f"❌ Ошибка обработки голосового сообщения: {str(e)}\n\n"
            "Попробуйте еще раз или используйте текст."
        )
        # Удаляем файл при ошибке
        if os.path.exists(file_path):
            os.remove(file_path)


@router.message(F.photo)
async def handle_photo_message(message: Message, state: FSMContext):
    """Обработка фотографий (еда)"""
    await message.answer("📸 Анализирую фото... Это может занять несколько секунд...")
    
    try:
        # Скачиваем фото (берем самое большое разрешение)
        photo: PhotoSize = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_path = f"{MEDIA_DIR}/photos/{message.from_user.id}_{datetime.now().timestamp()}.jpg"
        
        await message.bot.download_file(file.file_path, file_path)
        
        # Анализируем фото через Vision API
        user_context = await get_user_context(message.from_user.id)
        food_data = await analyze_food_from_photo(file_path, user_context)
        
        # Сохраняем запись
        async with async_session() as session:
            entry = CalorieEntry(
                user_id=message.from_user.id,
                food_name=food_data['food_name'],
                calories=food_data['calories'],
                protein=food_data.get('protein', 0),
                carbs=food_data.get('carbs', 0),
                fats=food_data.get('fats', 0),
                meal_type=food_data.get('meal_type', 'snack'),
                source_type='photo',
                source_data={'file_path': file_path, 'items': food_data.get('items', [])},
                ai_confidence=food_data.get('confidence', 0),
                ai_notes=food_data.get('notes', '')
            )
            session.add(entry)
            await session.flush()
            
            # Логируем AI взаимодействие
            ai_log = AIInteraction(
                user_id=message.from_user.id,
                interaction_type='food_analysis',
                input_type='photo',
                input_file_path=file_path,
                ai_response=food_data,
                ai_model='gpt-4o-mini',
                ai_confidence=food_data.get('confidence', 0),
                created_entry_type='calorie_entry',
                created_entry_id=entry.id
            )
            session.add(ai_log)
            await session.commit()
        
        # Формируем ответ
        confidence_emoji = "✅" if food_data['confidence'] > 0.7 else "⚠️"
        items_text = "\n".join([f"  • {item}" for item in food_data.get('items', [])])
        
        response = (
            f"{confidence_emoji} <b>Анализ завершен!</b>\n\n"
            f"🍽 <b>{food_data['food_name']}</b>\n"
            f"📊 Калории: <b>{food_data['calories']} ккал</b>\n"
            f"Б/Ж/У: {food_data.get('protein', 0):.1f} / {food_data.get('fats', 0):.1f} / {food_data.get('carbs', 0):.1f} г\n"
            f"Размер порции: {food_data.get('portion_size', 'средний')}\n\n"
        )
        
        if items_text:
            response += f"<b>Состав:</b>\n{items_text}\n\n"
        
        if food_data.get('notes'):
            # Экранируем HTML в notes
            notes = food_data['notes'].replace('<', '&lt;').replace('>', '&gt;')
            response += f"💡 <i>{notes}</i>\n\n"
        
        response += f"Уверенность AI: {int(food_data['confidence'] * 100)}%"
        
        await message.answer(response, reply_markup=get_main_menu())
        
    except Exception as e:
        await message.answer(
            f"❌ Ошибка анализа фото: {str(e)}\n\n"
            "Попробуйте сфотографировать еду с другого ракурса или при лучшем освещении."
        )
        if os.path.exists(file_path):
            os.remove(file_path)


@router.message(F.text & ~F.text.startswith('/'))
async def handle_text_message(message: Message, state: FSMContext):
    """Обработка текстовых сообщений (умный анализ)"""
    
    # Игнорируем кнопки меню
    menu_buttons = [
        "📊 Добавить калории", "🏃 Добавить тренировку",
        "📈 Моя статистика", "👤 Мой профиль",
        "⚖️ Записать вес", "❓ Помощь"
    ]
    if message.text in menu_buttons:
        return
    
    text = message.text.strip()
    
    # Определяем тип сообщения
    if any(word in text.lower() for word in ['съел', 'поел', 'завтрак', 'обед', 'ужин', 'калори', 'еда']):
        # Это о еде
        await message.answer("🤖 Анализирую питание...")
        await process_food_entry(message, text, 'text_ai')
        
    elif any(word in text.lower() for word in ['тренировка', 'пробежал', 'зал', 'бег', 'плавал', 'йога', 'км', 'минут тренировался']):
        # Это о тренировке
        await message.answer("🤖 Анализирую тренировку...")
        await process_workout_entry(message, text, 'text_ai')
        
    elif any(word in text.lower() for word in ['что', 'как', 'посоветуй', 'рекомендуй', 'помоги', 'скажи']):
        # Это запрос консультации
        await message.answer("🤔 Анализирую твои данные и готовлю рекомендацию...")
        await process_consultation(message, text)
    else:
        # Неопределенный тип - пробуем универсальный анализ
        await message.answer(
            "Я не совсем понял. Попробуй:\n"
            "• Опиши что ел: <i>\"Съел борщ и котлету\"</i>\n"
            "• Расскажи о тренировке: <i>\"Пробежал 5км за 30 минут\"</i>\n"
            "• Задай вопрос: <i>\"Что мне съесть на ужин?\"</i>\n"
            "• Или отправь фото еды 📸"
        )


async def process_food_entry(message: Message, text: str, source_type: str, file_path: str = None):
    """Обработка записи о еде через AI"""
    try:
        user_context = await get_user_context(message.from_user.id)
        food_data = await analyze_food_from_text(text, user_context)
        
        # Сохраняем в БД
        async with async_session() as session:
            entry = CalorieEntry(
                user_id=message.from_user.id,
                food_name=food_data['food_name'],
                calories=food_data['calories'],
                protein=food_data.get('protein', 0),
                carbs=food_data.get('carbs', 0),
                fats=food_data.get('fats', 0),
                meal_type=food_data.get('meal_type', 'snack'),
                source_type=source_type,
                source_data={'original_text': text, 'file_path': file_path} if file_path else {'original_text': text},
                ai_confidence=food_data.get('confidence', 0),
                ai_notes=food_data.get('notes', '')
            )
            session.add(entry)
            await session.flush()
            
            # Логируем AI
            ai_log = AIInteraction(
                user_id=message.from_user.id,
                interaction_type='food_analysis',
                input_type=source_type,
                input_data=text,
                input_file_path=file_path,
                ai_response=food_data,
                ai_model='gpt-4o-mini',
                ai_confidence=food_data.get('confidence', 0),
                created_entry_type='calorie_entry',
                created_entry_id=entry.id
            )
            session.add(ai_log)
            await session.commit()
        
        # Ответ пользователю
        confidence_emoji = "✅" if food_data['confidence'] > 0.8 else "⚠️"
        
        response = (
            f"{confidence_emoji} <b>Записано!</b>\n\n"
            f"🍽 <b>{food_data['food_name']}</b>\n"
            f"📊 Калории: <b>{food_data['calories']} ккал</b>\n"
            f"Б/Ж/У: {food_data.get('protein', 0):.1f} / {food_data.get('fats', 0):.1f} / {food_data.get('carbs', 0):.1f} г\n"
        )
        
        if food_data.get('notes'):
            # Экранируем HTML в notes
            notes = food_data['notes'].replace('<', '&lt;').replace('>', '&gt;')
            response += f"\n💡 <i>{notes}</i>"
        
        await message.answer(response, reply_markup=get_main_menu())
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


async def process_workout_entry(message: Message, text: str, source_type: str):
    """Обработка записи о тренировке через AI"""
    try:
        workout_data = await analyze_workout_from_text(text)
        
        # Сохраняем в БД
        async with async_session() as session:
            entry = WorkoutEntry(
                user_id=message.from_user.id,
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
            
            # Логируем AI
            ai_log = AIInteraction(
                user_id=message.from_user.id,
                interaction_type='workout_analysis',
                input_type=source_type,
                input_data=text,
                ai_response=workout_data,
                ai_model='gpt-4o-mini',
                ai_confidence=workout_data.get('confidence', 0),
                created_entry_type='workout_entry',
                created_entry_id=entry.id
            )
            session.add(ai_log)
            await session.commit()
        
        # Ответ пользователю
        intensity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        
        response = (
            f"✅ <b>Тренировка записана!</b>\n\n"
            f"🏃 <b>{workout_data['workout_type']}</b>\n"
            f"⏱ Длительность: <b>{workout_data['duration']}</b> мин\n"
            f"{intensity_emoji.get(workout_data.get('intensity', 'medium'), '⚪')} Интенсивность: {workout_data.get('intensity', 'средняя')}\n"
            f"🔥 Сожжено: <b>~{workout_data.get('calories_burned', 0)}</b> ккал\n"
        )
        
        if workout_data.get('distance'):
            response += f"📏 Дистанция: {workout_data['distance']} км\n"
        if workout_data.get('pace'):
            response += f"⚡️ Темп: {workout_data['pace']}\n"
        if workout_data.get('notes'):
            response += f"\n💡 <i>{workout_data['notes']}</i>"
        
        await message.answer(response, reply_markup=get_main_menu())
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


async def process_consultation(message: Message, query: str):
    """Обработка консультационного запроса"""
    try:
        # Собираем полный контекст пользователя
        user_context = await get_user_context(message.from_user.id)
        
        # TODO: Добавить последние записи еды и тренировок
        # TODO: Добавить данные анализов если есть
        
        # Получаем рекомендацию от AI
        recommendation = await get_smart_recommendation(user_context, query)
        
        # Логируем
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
        await message.answer(f"❌ Ошибка получения рекомендации: {str(e)}")
