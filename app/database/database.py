from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Boolean, Text, JSON, text, func
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Формируем URL подключения к БД
DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаем фабрику сессий
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для моделей"""
    pass


class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255))
    full_name = Column(String(255))
    age = Column(Integer)
    weight = Column(Float)  # вес в кг
    height = Column(Integer)  # рост в см
    gender = Column(String(10))  # male/female
    activity_level = Column(String(50))  # активность вне тренировок: sedentary, light, moderate
    goal = Column(String(50))  # lose_weight, maintain, gain_weight
    daily_calorie_target = Column(Integer)  # норма без учёта тренировок
    protein_per_kg = Column(Float)  # своя норма белка г/кг; NULL — по цели
    utc_offset_min = Column(Integer)  # часовой пояс: смещение от UTC в минутах
    tz_label = Column(String(50))  # подпись пояса для профиля («Москва»)
    wake_hour = Column(Integer)  # во сколько у пользователя утро
    current_day_start = Column(DateTime)  # /new_day override (команда отключена)
    last_active_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CalorieEntry(Base):
    """Модель записи о калориях"""
    __tablename__ = 'calorie_entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    food_name = Column(String(255), nullable=False)
    calories = Column(Integer, nullable=False)
    protein = Column(Float, default=0)  # белки в граммах
    carbs = Column(Float, default=0)  # углеводы в граммах
    fats = Column(Float, default=0)  # жиры в граммах
    meal_type = Column(String(50))  # breakfast, lunch, dinner, snack, water
    fiber = Column(Float, default=0)  # клетчатка, г
    sugar = Column(Float, default=0)  # добавленный сахар, г

    # Жидкость, мл
    water_ml = Column(Integer, default=0)  # чистая вода
    drinks_ml = Column(Integer, default=0)  # чай, кофе, соки и прочие безалкогольные
    soup_ml = Column(Integer, default=0)  # засчитанная часть супа (треть объёма)
    alcohol = Column(JSON)  # [{"type": "wine", "ml": 150}] — в жидкость не входит
    items = Column(JSON)  # разбивка по продуктам от AI

    # AI-Hub поля
    source_type = Column(String(20), default='manual')  # manual, voice, photo, text_ai
    source_data = Column(JSON)  # Оригинальные данные (путь к фото, текст голоса и т.д.)
    ai_confidence = Column(Float)  # Уверенность AI в анализе (0-1)
    ai_notes = Column(Text)  # Заметки/рекомендации от AI
    deleted_at = Column(DateTime)  # мягкое удаление (можно отменить)

    created_at = Column(DateTime, server_default=func.now())


class WorkoutEntry(Base):
    """Модель записи о тренировке"""
    __tablename__ = 'workout_entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    workout_type = Column(String(100), nullable=False)  # running, gym, yoga, etc.
    duration = Column(Integer, nullable=False)  # продолжительность в минутах
    calories_burned = Column(Integer, default=0)
    notes = Column(String(500))
    
    # AI-Hub поля
    source_type = Column(String(20), default='manual')  # manual, voice, text_ai
    intensity = Column(String(20))  # low, medium, high
    distance = Column(Float)  # расстояние в км (если применимо)
    pace = Column(String(50))  # темп (если применимо)
    ai_confidence = Column(Float)
    met = Column(Float)  # коэффициент MET для расчёта сожжённых калорий
    deleted_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())


class WeightLog(Base):
    """Модель записи веса"""
    __tablename__ = 'weight_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    weight = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class HealthData(Base):
    """Модель для хранения анализов и медицинских данных"""
    __tablename__ = 'health_data'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    data_type = Column(String(50), nullable=False)  # blood_test, hormone, vitamin, etc.
    parameter_name = Column(String(100), nullable=False)  # ferritin, vitamin_d, hemoglobin, etc.
    value = Column(Float, nullable=False)
    unit = Column(String(20))  # мкг/л, нг/мл, etc.
    reference_min = Column(Float)  # нижняя граница нормы
    reference_max = Column(Float)  # верхняя граница нормы
    is_normal = Column(Boolean)  # в пределах нормы или нет
    
    # Источник данных
    source_type = Column(String(20), default='manual')  # manual, ocr_photo
    source_file_path = Column(String(500))  # путь к фото анализа
    
    notes = Column(Text)  # Комментарии врача или AI
    test_date = Column(DateTime)  # дата сдачи анализа
    created_at = Column(DateTime, server_default=func.now())


class AIInteraction(Base):
    """Лог всех взаимодействий с AI для контекста и аналитики"""
    __tablename__ = 'ai_interactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    interaction_type = Column(String(50), nullable=False)  # food_analysis, workout_analysis, recommendation, consultation
    
    # Входные данные
    input_type = Column(String(20))  # voice, photo, text
    input_data = Column(Text)  # текст запроса или описание
    input_file_path = Column(String(500))  # путь к медиа-файлу
    
    # Выходные данные AI
    ai_response = Column(JSON)  # структурированный ответ AI
    ai_model = Column(String(50))  # gpt-4o, gpt-4o-mini, whisper-1
    ai_confidence = Column(Float)

    # Расход токенов
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)

    # Связь с созданными записями
    created_entry_type = Column(String(50))  # calorie_entry, workout_entry, health_data
    created_entry_id = Column(Integer)  # ID созданной записи
    status = Column(String(20))  # added, not_added, error

    created_at = Column(DateTime, server_default=func.now())


class MealPlan(Base):
    """Недельный план питания"""
    __tablename__ = 'meal_plans'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    week_start = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    ai_response = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class MealPlanItem(Base):
    """Элемент плана питания (одно блюдо)"""
    __tablename__ = 'meal_plan_items'

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Пн, 6=Вс
    meal_type = Column(String(20), nullable=False)  # breakfast, lunch, dinner, snack
    food_name = Column(String(500), nullable=False)
    recipe = Column(Text)
    ingredients = Column(Text)
    calories = Column(Integer, default=0)
    protein = Column(Float, default=0)
    fats = Column(Float, default=0)
    carbs = Column(Float, default=0)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class WorkoutPlan(Base):
    """Недельный план тренировок"""
    __tablename__ = 'workout_plans'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    week_start = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    ai_response = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class WorkoutPlanItem(Base):
    """Элемент плана тренировок (одна тренировка на день)"""
    __tablename__ = 'workout_plan_items'

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Пн, 6=Вс
    workout_type = Column(String(100), nullable=False)
    exercises = Column(JSON)  # [{name, sets, reps, rest}, ...]
    duration = Column(Integer, default=0)
    calories_burned = Column(Integer, default=0)
    notes = Column(Text)
    is_rest_day = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Добавляем новые колонки для существующих таблиц
        for stmt in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_day_start TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP",
            "ALTER TABLE ai_interactions ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER",
            "ALTER TABLE ai_interactions ADD COLUMN IF NOT EXISTS completion_tokens INTEGER",
            "ALTER TABLE ai_interactions ADD COLUMN IF NOT EXISTS total_tokens INTEGER",
            "ALTER TABLE ai_interactions ADD COLUMN IF NOT EXISTS status VARCHAR(20)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS protein_per_kg DOUBLE PRECISION",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS utc_offset_min INTEGER",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tz_label VARCHAR(50)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wake_hour INTEGER",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS fiber DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS sugar DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS water_ml INTEGER DEFAULT 0",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS drinks_ml INTEGER DEFAULT 0",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS soup_ml INTEGER DEFAULT 0",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS alcohol JSON",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS items JSON",
            "ALTER TABLE calorie_entries ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "ALTER TABLE workout_entries ADD COLUMN IF NOT EXISTS met DOUBLE PRECISION",
            "ALTER TABLE workout_entries ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            # Старые записи воды хранили объём в названии: «💧 Вода (1 ст. / 250 мл)»
            "UPDATE calorie_entries SET water_ml = COALESCE(substring(food_name from '(\\d+) мл')::int, 250) "
            "WHERE meal_type = 'water' AND (water_ml IS NULL OR water_ml = 0)",
        ]:
            await conn.execute(text(stmt))


async def get_session() -> AsyncSession:
    """Получение сессии БД"""
    async with async_session() as session:
        yield session
