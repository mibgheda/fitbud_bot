from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import async_session, User
from keyboards.reply import (
    get_main_menu, 
    get_gender_keyboard, 
    get_activity_level_keyboard,
    get_goal_keyboard
)

router = Router()


class ProfileSetup(StatesGroup):
    """Состояния для настройки профиля"""
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()
    waiting_for_activity = State()
    waiting_for_goal = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    async with async_session() as session:
        # Проверяем, есть ли пользователь в БД
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            await message.answer(
                f"С возвращением, {message.from_user.first_name}! 👋\n\n"
                "Используйте меню ниже для управления:",
                reply_markup=get_main_menu()
            )
        else:
            # Создаем нового пользователя
            new_user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name
            )
            session.add(new_user)
            await session.commit()
            
            await message.answer(
                f"Привет, {message.from_user.first_name}! 👋\n\n"
                "Я FitBud — твой персональный помощник по питанию и фитнесу.\n\n"
                "Давай настроим твой профиль, чтобы я мог рассчитать оптимальную "
                "калорийность и помочь достичь твоих целей!\n\n"
                "Сколько тебе лет? (введи число)"
            )
            await state.set_state(ProfileSetup.waiting_for_age)


@router.message(ProfileSetup.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста"""
    try:
        age = int(message.text)
        if age < 10 or age > 120:
            await message.answer("Пожалуйста, введи корректный возраст (от 10 до 120 лет)")
            return
        
        await state.update_data(age=age)
        await message.answer("Укажи свой пол:", reply_markup=get_gender_keyboard())
        await state.set_state(ProfileSetup.waiting_for_gender)
    except ValueError:
        await message.answer("Пожалуйста, введи возраст числом")


@router.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = callback.data.split("_")[1]
    await state.update_data(gender=gender)
    
    await callback.message.edit_text("Какой у тебя рост? (в сантиметрах)")
    await state.set_state(ProfileSetup.waiting_for_height)
    await callback.answer()


@router.message(ProfileSetup.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    try:
        height = int(message.text)
        if height < 100 or height > 250:
            await message.answer("Пожалуйста, введи корректный рост (от 100 до 250 см)")
            return
        
        await state.update_data(height=height)
        await message.answer("Какой у тебя вес? (в килограммах)")
        await state.set_state(ProfileSetup.waiting_for_weight)
    except ValueError:
        await message.answer("Пожалуйста, введи рост числом")


@router.message(ProfileSetup.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    try:
        weight = float(message.text.replace(',', '.'))
        if weight < 30 or weight > 300:
            await message.answer("Пожалуйста, введи корректный вес (от 30 до 300 кг)")
            return
        
        await state.update_data(weight=weight)
        await message.answer(
            "Выбери свой уровень активности:",
            reply_markup=get_activity_level_keyboard()
        )
        await state.set_state(ProfileSetup.waiting_for_activity)
    except ValueError:
        await message.answer("Пожалуйста, введи вес числом (можно с десятичной точкой)")


@router.callback_query(F.data.startswith("activity_"))
async def process_activity(callback: CallbackQuery, state: FSMContext):
    """Обработка уровня активности"""
    activity = callback.data.split("_", 1)[1]
    await state.update_data(activity_level=activity)
    
    await callback.message.edit_text(
        "Какая у тебя цель?",
        reply_markup=get_goal_keyboard()
    )
    await state.set_state(ProfileSetup.waiting_for_goal)
    await callback.answer()


@router.callback_query(F.data.startswith("goal_"))
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Обработка цели и завершение настройки профиля"""
    goal = callback.data.split("_", 1)[1]
    data = await state.get_data()
    
    # Рассчитываем базовый метаболизм (формула Миффлина-Сан Жеора)
    if data['gender'] == 'male':
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] + 5
    else:
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] - 161
    
    # Коэффициенты активности
    activity_multipliers = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9
    }
    
    # Расчет калорий с учетом активности
    tdee = bmr * activity_multipliers[data['activity_level']]
    
    # Корректировка в зависимости от цели
    if goal == 'lose_weight':
        daily_calories = int(tdee - 500)  # Дефицит 500 ккал
    elif goal == 'gain_weight':
        daily_calories = int(tdee + 300)  # Профицит 300 ккал
    else:
        daily_calories = int(tdee)
    
    # Сохраняем данные в БД
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one()
        
        user.age = data['age']
        user.gender = data['gender']
        user.height = data['height']
        user.weight = data['weight']
        user.activity_level = data['activity_level']
        user.goal = goal
        user.daily_calorie_target = daily_calories
        
        await session.commit()
    
    goal_text = {
        'lose_weight': 'похудение',
        'maintain': 'поддержание веса',
        'gain_weight': 'набор массы'
    }
    
    await callback.message.edit_text(
        f"✅ Отлично! Профиль настроен!\n\n"
        f"Твоя цель: <b>{goal_text[goal]}</b>\n"
        f"Рекомендуемая калорийность: <b>{daily_calories} ккал/день</b>\n\n"
        f"Базовый метаболизм (BMR): {int(bmr)} ккал\n"
        f"Общий расход (TDEE): {int(tdee)} ккал\n\n"
        "Используй меню ниже для отслеживания питания и тренировок! 💪"
    )
    
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu()
    )
    
    await state.clear()
    await callback.answer()


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    """Справка по использованию бота"""
    help_text = """
<b>📖 Справка FitBud</b>

<b>Основные функции:</b>

📊 <b>Добавить калории</b> - записать прием пищи
🏃 <b>Добавить тренировку</b> - записать тренировку
📈 <b>Моя статистика</b> - посмотреть прогресс
👤 <b>Мой профиль</b> - просмотр и редактирование профиля
⚖️ <b>Записать вес</b> - добавить измерение веса

<b>Команды:</b>
/start - начать работу с ботом
/profile - настроить профиль заново
/help - показать эту справку

<b>Как это работает:</b>
Бот рассчитывает твою дневную норму калорий на основе пола, возраста, роста, веса, уровня активности и цели. Отслеживай питание и тренировки, чтобы достичь своих фитнес-целей! 💪
    """
    await message.answer(help_text, reply_markup=get_main_menu())
