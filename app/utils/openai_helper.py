"""
Модуль интеграции с OpenAI API для обработки голоса, фото и текста
"""
import os
import base64
from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Инициализация клиента OpenAI
client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))


async def transcribe_voice(audio_file_path: str) -> str:
    """
    Транскрибация голосового сообщения в текст
    
    Args:
        audio_file_path: Путь к аудио файлу
    
    Returns:
        Текст транскрипции
    """
    try:
        with open(audio_file_path, 'rb') as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        return transcript.text
    except Exception as e:
        raise Exception(f"Ошибка транскрибации: {str(e)}")


async def analyze_food_from_text(text: str, user_context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Анализ еды из текстового описания с помощью GPT-4
    
    Args:
        text: Описание еды
        user_context: Контекст пользователя (цель, активность и т.д.)
    
    Returns:
        Dict с информацией о еде: {
            'food_name': str,
            'calories': int,
            'protein': float,
            'carbs': float,
            'fats': float,
            'meal_type': str,
            'confidence': float
        }
    """
    context_info = ""
    if user_context:
        context_info = f"""
Контекст пользователя:
- Цель: {user_context.get('goal', 'не указана')}
- Дневная норма калорий: {user_context.get('daily_target', 'не указана')}
"""
    
    prompt = f"""Ты диетолог-аналитик. Проанализируй описание еды и верни данные в JSON формате.

{context_info}

Описание еды: "{text}"

Верни ТОЛЬКО JSON в формате:
{{
    "food_name": "название блюда/продукта",
    "calories": целое число калорий,
    "protein": граммы белка (float),
    "carbs": граммы углеводов (float),
    "fats": граммы жиров (float),
    "meal_type": "breakfast/lunch/dinner/snack",
    "confidence": уверенность в оценке 0-1,
    "notes": "дополнительные заметки или предупреждения"
}}

Правила:
- Если порция не указана, предполагай стандартную
- Будь максимально точным в расчетах
- Meal_type определяй по времени суток или контексту
- Если не уверен - укажи в notes"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты точный диетолог-калькулятор. Отвечаешь ТОЛЬКО валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        raise Exception(f"Ошибка анализа еды: {str(e)}")


async def analyze_food_from_photo(image_path: str, user_context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Анализ еды по фотографии с помощью GPT-4 Vision
    
    Args:
        image_path: Путь к фото
        user_context: Контекст пользователя
    
    Returns:
        Dict с информацией о еде
    """
    context_info = ""
    if user_context:
        context_info = f"""
Контекст: Цель пользователя - {user_context.get('goal', 'не указана')}, 
норма {user_context.get('daily_target', '?')} ккал/день
"""
    
    # Кодируем изображение в base64
    with open(image_path, 'rb') as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    prompt = f"""Проанализируй фото еды и оцени содержимое. {context_info}

Верни ТОЛЬКО JSON в формате:
{{
    "food_name": "подробное описание всех блюд на фото",
    "calories": примерная общая калорийность (целое число),
    "protein": граммы белка (float),
    "carbs": граммы углеводов (float),
    "fats": граммы жиров (float),
    "meal_type": "breakfast/lunch/dinner/snack",
    "portion_size": "small/medium/large",
    "confidence": уверенность 0-1,
    "items": ["список всех блюд/продуктов"],
    "notes": "рекомендации или замечания"
}}

Будь максимально точным в оценке размера порций и калорийности."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        raise Exception(f"Ошибка анализа фото: {str(e)}")


async def analyze_workout_from_text(text: str) -> Dict[str, Any]:
    """
    Анализ тренировки из текстового описания
    
    Args:
        text: Описание тренировки
    
    Returns:
        Dict с информацией о тренировке
    """
    prompt = f"""Проанализируй описание тренировки и верни данные в JSON.

Описание: "{text}"

Верни ONLY JSON:
{{
    "workout_type": "тип тренировки (running/gym/cycling/yoga/swimming/other)",
    "duration": длительность в минутах (целое число),
    "calories_burned": примерное количество сожженных калорий,
    "intensity": "low/medium/high",
    "distance": расстояние в км если применимо (или null),
    "pace": темп если применимо (или null),
    "notes": "краткое резюме и рекомендации",
    "confidence": уверенность 0-1
}}

Правила:
- Калории считай исходя из средней массы тела 70кг
- Если данных мало, используй стандартные метрики
- Будь консервативен в оценке калорий"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты тренер-аналитик. Отвечаешь ТОЛЬКО валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        raise Exception(f"Ошибка анализа тренировки: {str(e)}")


async def get_smart_recommendation(user_data: Dict, query: str) -> str:
    """
    Получение персональных рекомендаций на основе данных пользователя
    
    Args:
        user_data: Полные данные пользователя (профиль, история, анализы)
        query: Вопрос пользователя
    
    Returns:
        Текст рекомендации
    """
    context = f"""
Данные пользователя:
- Возраст: {user_data.get('age')}
- Пол: {user_data.get('gender')}
- Вес: {user_data.get('weight')} кг
- Рост: {user_data.get('height')} см
- Цель: {user_data.get('goal')}
- Уровень активности: {user_data.get('activity_level')}
- Дневная норма калорий: {user_data.get('daily_target')} ккал

Последние записи питания: {user_data.get('recent_meals', [])}
Последние тренировки: {user_data.get('recent_workouts', [])}
Анализы (если есть): {user_data.get('health_data', {})}
"""

    prompt = f"""Ты персональный биохакер и нутрициолог. На основе данных дай максимально конкретную рекомендацию.

{context}

Вопрос пользователя: "{query}"

Дай практичный ответ с учетом:
1. Текущего прогресса к цели
2. Баланса нутриентов
3. Физической формы
4. Результатов анализов (если есть)

Будь конкретен: давай цифры, рецепты, упражнения. Не общие слова."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты персональный биохакер с медицинским образованием. Даешь четкие, научно обоснованные рекомендации."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        raise Exception(f"Ошибка получения рекомендации: {str(e)}")
