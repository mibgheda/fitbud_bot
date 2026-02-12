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


async def generate_meal_plan(user_context: Dict, recent_stats: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Генерация недельного плана питания

    Returns:
        Dict с планом на 7 дней, каждый день содержит breakfast/lunch/dinner/snack
    """
    stats_info = ""
    if recent_stats:
        stats_info = f"""
Статистика за последнюю неделю:
- Среднее потребление калорий: {recent_stats.get('avg_calories', '?')} ккал/день
- Средние БЖУ: Б:{recent_stats.get('avg_protein', '?')}г Ж:{recent_stats.get('avg_fats', '?')}г У:{recent_stats.get('avg_carbs', '?')}г
"""

    goal_desc = {
        'lose_weight': 'похудение (дефицит калорий, высокий белок)',
        'maintain': 'поддержание веса (сбалансированное питание)',
        'gain_weight': 'набор массы (профицит калорий, высокий белок и углеводы)'
    }
    gender_desc = {'male': 'мужской', 'female': 'женский'}

    prompt = f"""Составь детальный план питания на 7 дней (Пн-Вс).

Профиль:
- Пол: {gender_desc.get(user_context.get('gender', ''), 'не указан')}
- Возраст: {user_context.get('age', '?')} лет
- Вес: {user_context.get('weight', '?')} кг, Рост: {user_context.get('height', '?')} см
- Цель: {goal_desc.get(user_context.get('goal', 'maintain'), 'поддержание')}
- Дневная норма: {user_context.get('daily_target', 2000)} ккал
- Уровень активности: {user_context.get('activity_level', 'moderate')}
{stats_info}

Верни ТОЛЬКО JSON:
{{
  "days": [
    {{
      "day": 0,
      "meals": [
        {{
          "meal_type": "breakfast",
          "food_name": "Название блюда",
          "calories": 350,
          "protein": 15.0,
          "fats": 10.0,
          "carbs": 45.0,
          "ingredients": "Ингредиенты с граммовками через запятую",
          "recipe": "Пошаговый рецепт приготовления"
        }},
        {{"meal_type": "lunch", ...}},
        {{"meal_type": "dinner", ...}},
        {{"meal_type": "snack", ...}}
      ]
    }},
    ...ещё 6 дней (day: 1-6)
  ]
}}

Правила:
- Каждый день: завтрак + обед + ужин + перекус
- Суммарные калории дня = {user_context.get('daily_target', 2000)} ± 50 ккал
- Блюда разнообразные, доступные, из обычных продуктов
- Рецепты простые и понятные, с указанием времени приготовления
- Ингредиенты с точными граммовками
- БЖУ реалистичны для каждого блюда
- Учитывай цель пользователя при распределении макронутриентов"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты профессиональный диетолог-нутрициолог. Составляешь персональные планы питания. Отвечаешь ТОЛЬКО валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        import json
        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        raise Exception(f"Ошибка генерации плана питания: {str(e)}")


async def generate_workout_plan(user_context: Dict, recent_stats: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Генерация недельного плана тренировок

    Returns:
        Dict с планом на 7 дней
    """
    stats_info = ""
    if recent_stats:
        stats_info = f"""
Статистика за последнюю неделю:
- Тренировок: {recent_stats.get('workout_count', 0)}
- Общее время: {recent_stats.get('total_duration', 0)} мин
- Сожжено калорий: {recent_stats.get('total_burned', 0)} ккал
- Типы тренировок: {recent_stats.get('workout_types', 'нет данных')}
"""

    goal_desc = {
        'lose_weight': 'похудение (кардио + силовые, жиросжигание)',
        'maintain': 'поддержание формы (баланс кардио и силовых)',
        'gain_weight': 'набор мышечной массы (силовые, прогрессивная нагрузка)'
    }
    activity_desc = {
        'sedentary': 'начинающий (минимальная подготовка)',
        'light': 'лёгкий уровень (1-3 раза в неделю)',
        'moderate': 'средний уровень (3-5 раз в неделю)',
        'active': 'продвинутый (6-7 раз в неделю)',
        'very_active': 'спортсмен (интенсивные ежедневные тренировки)'
    }
    gender_desc = {'male': 'мужской', 'female': 'женский'}

    prompt = f"""Составь план тренировок на 7 дней (Пн-Вс).

Профиль:
- Пол: {gender_desc.get(user_context.get('gender', ''), 'не указан')}
- Возраст: {user_context.get('age', '?')} лет
- Вес: {user_context.get('weight', '?')} кг
- Подготовка: {activity_desc.get(user_context.get('activity_level', 'moderate'), 'средняя')}
- Цель: {goal_desc.get(user_context.get('goal', 'maintain'), 'поддержание')}
{stats_info}

Верни ТОЛЬКО JSON:
{{
  "days": [
    {{
      "day": 0,
      "is_rest_day": false,
      "workout_type": "Название тренировки (например: Грудь + Трицепс)",
      "duration": 50,
      "calories_burned": 350,
      "exercises": [
        {{
          "name": "Жим штанги лёжа",
          "sets": 4,
          "reps": "8-10",
          "rest": "90 сек",
          "notes": "Средний вес, контроль техники"
        }}
      ],
      "notes": "Разминка 5 мин, заминка 5 мин"
    }},
    {{
      "day": 1,
      "is_rest_day": true,
      "workout_type": "День отдыха",
      "duration": 0,
      "calories_burned": 0,
      "exercises": [],
      "notes": "Лёгкая прогулка 20 мин, растяжка"
    }},
    ...ещё 5 дней (day: 2-6)
  ]
}}

Правила:
- 3-5 тренировочных дней, 2-4 дня отдыха (в зависимости от уровня)
- Для каждой тренировки: 4-8 упражнений с подходами и повторениями
- Указывай время отдыха между подходами
- Калории считай для веса {user_context.get('weight', 70)} кг
- Учитывай цель: похудение → больше кардио, набор → больше силовых
- Дни отдыха с рекомендациями по восстановлению
- Прогрессивная структура внутри недели"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты профессиональный фитнес-тренер. Составляешь персональные программы тренировок. Отвечаешь ТОЛЬКО валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        import json
        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        raise Exception(f"Ошибка генерации плана тренировок: {str(e)}")


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
