from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, Boolean
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Формируем URL подключения к БД
DATABASE_URL = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=True)

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
    activity_level = Column(String(50))  # sedentary, light, moderate, active, very_active
    goal = Column(String(50))  # lose_weight, maintain, gain_weight
    daily_calorie_target = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
    meal_type = Column(String(50))  # breakfast, lunch, dinner, snack
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkoutEntry(Base):
    """Модель записи о тренировке"""
    __tablename__ = 'workout_entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    workout_type = Column(String(100), nullable=False)  # running, gym, yoga, etc.
    duration = Column(Integer, nullable=False)  # продолжительность в минутах
    calories_burned = Column(Integer, default=0)
    notes = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)


class WeightLog(Base):
    """Модель записи веса"""
    __tablename__ = 'weight_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    weight = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Получение сессии БД"""
    async with async_session() as session:
        yield session
