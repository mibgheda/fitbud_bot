from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from datetime import datetime, timedelta
import asyncio
import os
import logging

from sqlalchemy import func as sa_func
from database.database import (
    async_session, User, CalorieEntry, WorkoutEntry, WeightLog,
    HealthData, AIInteraction, MealPlan, MealPlanItem,
    WorkoutPlan, WorkoutPlanItem, calc_today_start,
)
from keyboards.reply import (
    get_main_menu,
    get_agreement_keyboard,
    get_gender_keyboard,
    get_activity_level_keyboard,
    get_goal_keyboard,
    get_delete_confirm_keyboard,
    not_menu_button,
)

router = Router()


class ProfileSetup(StatesGroup):
    """Состояния для настройки профиля"""
    waiting_for_agreement = State()
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()
    waiting_for_activity = State()
    waiting_for_goal = State()


def calculate_calories(gender: str, weight: float, height: int, age: int,
                       activity_level: str = 'moderate', goal: str = 'maintain'):
    """Расчёт BMR, TDEE и суточной нормы калорий по формуле Миффлина-Сан Жеора"""
    if gender == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    activity_multipliers = {
        'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55,
        'active': 1.725, 'very_active': 1.9
    }
    tdee = bmr * activity_multipliers.get(activity_level, 1.55)

    if goal == 'lose_weight':
        return int(tdee - 500)
    elif goal == 'gain_weight':
        return int(tdee + 300)
    return int(tdee)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user and user.daily_calorie_target:
            # Профиль уже настроен
            name = user.full_name or message.from_user.first_name
            await message.answer(
                f"С возвращением, {name}! 👋\n\n"
                "Используй меню ниже для управления:",
                reply_markup=get_main_menu()
            )
        elif user and user.age and user.height and user.weight and user.gender:
            # Есть данные профиля из предыдущей версии — дорассчитываем калории
            if not user.activity_level:
                user.activity_level = 'moderate'
            if not user.goal:
                user.goal = 'maintain'
            user.daily_calorie_target = calculate_calories(
                user.gender, user.weight, user.height, user.age,
                user.activity_level, user.goal
            )
            await session.commit()

            name = user.full_name or message.from_user.first_name
            await message.answer(
                f"С возвращением, {name}! 👋\n\n"
                f"Я обновил твой профиль.\n"
                f"Твоя суточная норма: <b>{user.daily_calorie_target} ккал/день</b>\n\n"
                "Используй меню ниже для управления:",
                reply_markup=get_main_menu()
            )
        else:
            # Новый пользователь — онбординг
            if not user:
                new_user = User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    full_name=message.from_user.full_name
                )
                session.add(new_user)
                await session.commit()

            await message.answer(
                f"Привет, {message.from_user.first_name}! 👋\n\n"
                "Я <b>FitBud</b> — твой персональный помощник по питанию и фитнесу.\n\n"
                "Прежде чем начать, ознакомься с документами и прими условия использования:",
                reply_markup=get_agreement_keyboard()
            )
            await state.set_state(ProfileSetup.waiting_for_agreement)


# --- Обработка согласия ---

@router.message(ProfileSetup.waiting_for_agreement, not_menu_button)
async def remind_agreement(message: Message, state: FSMContext):
    """Напоминание принять соглашение"""
    await message.answer(
        "Пожалуйста, ознакомься с документами и нажми кнопку «✅ Я принимаю условия».",
        reply_markup=get_agreement_keyboard()
    )


@router.callback_query(F.data == "accept_agreement")
async def process_agreement(callback: CallbackQuery, state: FSMContext):
    """Пользователь принял соглашение"""
    await callback.message.edit_text(
        "✅ Спасибо за принятие условий!\n\n"
        "Давай настроим твой профиль.\n"
        "Как тебя зовут? (имя для обращения)"
    )
    await state.set_state(ProfileSetup.waiting_for_name)
    await callback.answer()


# --- Имя ---

@router.message(ProfileSetup.waiting_for_name, not_menu_button)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Пожалуйста, введи корректное имя (от 2 до 50 символов)")
        return

    await state.update_data(name=name)
    await message.answer(
        f"Приятно познакомиться, <b>{name}</b>!\n\n"
        "Укажи свой пол:",
        reply_markup=get_gender_keyboard()
    )
    await state.set_state(ProfileSetup.waiting_for_gender)


# --- Пол ---

@router.callback_query(F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора пола"""
    gender = callback.data.split("_")[1]
    await state.update_data(gender=gender)

    await callback.message.edit_text("Сколько тебе лет? (введи число)")
    await state.set_state(ProfileSetup.waiting_for_age)
    await callback.answer()


# --- Возраст ---

@router.message(ProfileSetup.waiting_for_age, not_menu_button)
async def process_age(message: Message, state: FSMContext):
    """Обработка возраста"""
    try:
        age = int(message.text)
        if age < 10 or age > 120:
            await message.answer("Пожалуйста, введи корректный возраст (от 10 до 120 лет)")
            return

        await state.update_data(age=age)
        await message.answer("Какой у тебя рост? (в сантиметрах)")
        await state.set_state(ProfileSetup.waiting_for_height)
    except ValueError:
        await message.answer("Пожалуйста, введи возраст числом")


# --- Рост ---

@router.message(ProfileSetup.waiting_for_height, not_menu_button)
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


# --- Вес ---

@router.message(ProfileSetup.waiting_for_weight, not_menu_button)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    try:
        weight = float(message.text.replace(',', '.'))
        if weight < 30 or weight > 300:
            await message.answer("Пожалуйста, введи корректный вес (от 30 до 300 кг)")
            return

        await state.update_data(weight=weight)
        await message.answer(
            "Выбери свой уровень физической активности:",
            reply_markup=get_activity_level_keyboard()
        )
        await state.set_state(ProfileSetup.waiting_for_activity)
    except ValueError:
        await message.answer("Пожалуйста, введи вес числом (можно с десятичной точкой)")


# --- Активность ---

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


# --- Цель + расчёт калорий и БЖУ ---

@router.callback_query(F.data.startswith("goal_"))
async def process_goal(callback: CallbackQuery, state: FSMContext):
    """Обработка цели и завершение настройки профиля"""
    goal = callback.data.split("_", 1)[1]
    data = await state.get_data()

    daily_calories = calculate_calories(
        data['gender'], data['weight'], data['height'], data['age'],
        data['activity_level'], goal
    )

    # BMR/TDEE для отображения
    if data['gender'] == 'male':
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] + 5
    else:
        bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age'] - 161
    activity_multipliers = {
        'sedentary': 1.2, 'light': 1.375, 'moderate': 1.55,
        'active': 1.725, 'very_active': 1.9
    }
    tdee = bmr * activity_multipliers[data['activity_level']]

    # Расчёт БЖУ (процент от калорий)
    if goal == 'lose_weight':
        protein_pct, fat_pct, carb_pct = 0.35, 0.25, 0.40
    elif goal == 'gain_weight':
        protein_pct, fat_pct, carb_pct = 0.25, 0.25, 0.50
    else:
        protein_pct, fat_pct, carb_pct = 0.30, 0.30, 0.40

    protein_g = int(daily_calories * protein_pct / 4)
    fat_g = int(daily_calories * fat_pct / 9)
    carb_g = int(daily_calories * carb_pct / 4)

    # Сохраняем в БД
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one()

        user.full_name = data.get('name', user.full_name)
        user.age = data['age']
        user.gender = data['gender']
        user.height = data['height']
        user.weight = data['weight']
        user.activity_level = data['activity_level']
        user.goal = goal
        user.daily_calorie_target = daily_calories

        await session.commit()

    goal_text = {
        'lose_weight': 'Похудение',
        'maintain': 'Поддержание веса',
        'gain_weight': 'Набор массы'
    }

    activity_text = {
        'sedentary': 'Минимальный',
        'light': 'Легкий',
        'moderate': 'Средний',
        'active': 'Высокий',
        'very_active': 'Экстремальный'
    }

    await callback.message.edit_text(
        f"✅ Отлично, <b>{data.get('name', 'друг')}</b>! Профиль настроен!\n\n"
        f"<b>Твои параметры:</b>\n"
        f"Пол: {'Мужской' if data['gender'] == 'male' else 'Женский'}\n"
        f"Возраст: {data['age']} лет\n"
        f"Рост: {data['height']} см | Вес: {data['weight']} кг\n"
        f"Активность: {activity_text[data['activity_level']]}\n"
        f"Цель: {goal_text[goal]}\n\n"
        f"<b>Твоя суточная норма:</b>\n"
        f"Калории: <b>{daily_calories} ккал/день</b>\n"
        f"Белки: <b>{protein_g} г</b> | Жиры: <b>{fat_g} г</b> | Углеводы: <b>{carb_g} г</b>\n\n"
        f"<i>BMR: {int(bmr)} ккал | TDEE: {int(tdee)} ккал</i>\n\n"
        "Используй меню ниже для отслеживания питания и тренировок! 💪"
    )

    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu()
    )

    await state.clear()
    await callback.answer()


# --- Помощь ---

@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message, state: FSMContext):
    """Справка по использованию бота"""
    await state.clear()
    help_text = (
        "<b>📖 Справка FitBud</b>\n\n"
        "<b>Основные функции:</b>\n\n"
        "✨ <b>Быстрый ввод</b> — запись еды и тренировок через AI\n"
        "🍽 <b>План питания</b> — недельный план с рецептами от AI\n"
        "🏋️ <b>План тренировок</b> — персональная программа от AI\n"
        "📈 <b>Моя статистика</b> — посмотреть прогресс\n"
        "👤 <b>Мой профиль</b> — просмотр профиля\n"
        "⚖️ <b>Записать вес</b> — добавить измерение веса\n\n"
        "<b>AI-возможности:</b>\n"
        "Напиши что съел или о тренировке — AI проанализирует!\n"
        "Отправь фото еды — AI оценит калории и БЖУ.\n"
        "Отправь голосовое — AI распознает и запишет.\n\n"
        "<b>Команды:</b>\n"
        "/start — начать работу / перенастроить профиль\n"
        "/help — показать эту справку\n"
        "/new_day — начать новый день с нуля\n"
        "/delete_account — удалить аккаунт и все данные\n\n"
        "<b>Документы:</b>\n"
        "📋 <a href=\"https://telegra.ph/Polzovatelskoe-soglashenie-dlya-Telegram-bota-FitBud-02-09\">Пользовательское соглашение</a>\n"
        "🔒 <a href=\"https://telegra.ph/Politika-obrabotki-personalnyh-dannyh-v-ramkah-Telegram-bota-FitBud-02-09\">Политика обработки ПДн</a>\n\n"
        "<i>Для удаления аккаунта и всех данных используй /delete_account</i>"
    )
    await message.answer(help_text, reply_markup=get_main_menu(), disable_web_page_preview=True)


# --- Новый день ---

@router.message(Command("new_day"))
async def cmd_new_day(message: Message, state: FSMContext):
    """Начать новый день с 0"""
    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала настрой профиль командой /start")
            return

        user.current_day_start = datetime.now()
        await session.commit()

        target = user.daily_calorie_target or 2000

    await message.answer(
        "🔄 <b>Новый день начат!</b>\n\n"
        f"Калории: <b>0</b> / {target} ккал\n"
        "Все счётчики обнулены.\n"
        "Удачного дня! 💪",
        reply_markup=get_main_menu()
    )


# --- Удаление аккаунта ---

@router.message(Command("delete_account"))
async def cmd_delete_account(message: Message, state: FSMContext):
    """Запрос на удаление аккаунта"""
    await state.clear()
    await message.answer(
        "⚠️ <b>Удаление аккаунта</b>\n\n"
        "Ты уверен(а)? Это действие удалит:\n"
        "• Профиль и настройки\n"
        "• Все записи о питании\n"
        "• Все записи о тренировках\n"
        "• Историю веса\n"
        "• Медицинские данные\n"
        "• Историю AI-взаимодействий\n\n"
        "<b>Это действие необратимо!</b>",
        reply_markup=get_delete_confirm_keyboard()
    )


@router.callback_query(F.data == "confirm_delete_account")
async def process_delete_account(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления аккаунта"""
    user_id = callback.from_user.id

    async with async_session() as session:
        await session.execute(delete(MealPlanItem).where(MealPlanItem.user_id == user_id))
        await session.execute(delete(MealPlan).where(MealPlan.user_id == user_id))
        await session.execute(delete(WorkoutPlanItem).where(WorkoutPlanItem.user_id == user_id))
        await session.execute(delete(WorkoutPlan).where(WorkoutPlan.user_id == user_id))
        await session.execute(delete(CalorieEntry).where(CalorieEntry.user_id == user_id))
        await session.execute(delete(WorkoutEntry).where(WorkoutEntry.user_id == user_id))
        await session.execute(delete(WeightLog).where(WeightLog.user_id == user_id))
        await session.execute(delete(HealthData).where(HealthData.user_id == user_id))
        await session.execute(delete(AIInteraction).where(AIInteraction.user_id == user_id))
        await session.execute(delete(User).where(User.telegram_id == user_id))
        await session.commit()

    await callback.message.edit_text(
        "✅ <b>Аккаунт удалён</b>\n\n"
        "Все твои данные были удалены.\n"
        "Чтобы начать заново, используй /start"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel_delete_account")
async def cancel_delete_account(callback: CallbackQuery, state: FSMContext):
    """Отмена удаления аккаунта"""
    await callback.message.edit_text("✅ Удаление отменено. Твои данные в безопасности!")
    await callback.answer()


# --- Рассылка (только для админа) ---

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    """Рассылка сообщения всем пользователям (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer(
            "Использование:\n"
            "<code>/broadcast Текст сообщения</code>\n\n"
            "Поддерживается HTML-разметка."
        )
        return

    # Получаем всех пользователей
    async with async_session() as session:
        result = await session.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.all()]

    total = len(user_ids)
    sent = 0
    failed = 0

    status_msg = await message.answer(f"📤 Начинаю рассылку {total} пользователям...")

    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast failed for {user_id}: {e}")

        # Задержка для соблюдения лимитов Telegram (30 msg/sec)
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b> / {total}\n"
        f"Не доставлено: <b>{failed}</b>"
    )


# --- Баланс токенов (только для админа) ---

@router.message(Command("balance"))
async def cmd_balance(message: Message, state: FSMContext):
    """Показать расход токенов OpenAI"""
    if message.from_user.id != ADMIN_ID:
        return

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.now() - timedelta(days=7)

    async with async_session() as session:
        # Общая статистика по токенам, сгруппированная по модели
        model_stats = await session.execute(
            select(
                AIInteraction.ai_model,
                sa_func.count(AIInteraction.id),
                sa_func.sum(AIInteraction.prompt_tokens),
                sa_func.sum(AIInteraction.completion_tokens),
                sa_func.sum(AIInteraction.total_tokens),
            )
            .group_by(AIInteraction.ai_model)
        )
        models = model_stats.all()

        # Запросов за сегодня
        today_count = await session.execute(
            select(sa_func.count(AIInteraction.id))
            .where(AIInteraction.created_at >= today_start)
        )
        today_total = today_count.scalar() or 0

        # Запросов за неделю
        week_count = await session.execute(
            select(sa_func.count(AIInteraction.id))
            .where(AIInteraction.created_at >= week_ago)
        )
        week_total = week_count.scalar() or 0

        # Всего запросов
        all_count = await session.execute(
            select(sa_func.count(AIInteraction.id))
        )
        all_total = all_count.scalar() or 0

    # Приблизительные цены за 1M токенов
    PRICES = {
        'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
        'gpt-4o': {'input': 2.50, 'output': 10.00},
        'whisper-1': {'input': 0, 'output': 0},
    }

    text = (
        "💰 <b>Расход токенов OpenAI</b>\n\n"
        f"📊 Запросов: сегодня <b>{today_total}</b> | "
        f"за неделю <b>{week_total}</b> | всего <b>{all_total}</b>\n\n"
    )

    grand_prompt = grand_completion = grand_total = 0
    estimated_cost = 0.0

    for model, count, prompt_tk, compl_tk, total_tk in models:
        prompt_tk = prompt_tk or 0
        compl_tk = compl_tk or 0
        total_tk = total_tk or 0
        grand_prompt += prompt_tk
        grand_completion += compl_tk
        grand_total += total_tk

        prices = PRICES.get(model or '', {'input': 0, 'output': 0})
        cost = (prompt_tk / 1_000_000 * prices['input'] +
                compl_tk / 1_000_000 * prices['output'])
        estimated_cost += cost

        text += (
            f"<b>{model or '?'}</b>: {count} запросов\n"
            f"  prompt: {prompt_tk:,} | completion: {compl_tk:,}\n"
            f"  ~${cost:.4f}\n\n"
        )

    text += (
        f"<b>Итого токенов:</b> {grand_total:,}\n"
        f"<b>Примерная стоимость:</b> ~${estimated_cost:.4f}\n\n"
        "<i>Цены приблизительные (gpt-4o-mini: $0.15/$0.60, gpt-4o: $2.50/$10.00 за 1M токенов)</i>"
    )

    await message.answer(text)


# --- Статистика пользователей (только для админа) ---

@router.message(Command("users"))
async def cmd_users(message: Message, state: FSMContext):
    """Показать статистику пользователей"""
    if message.from_user.id != ADMIN_ID:
        return

    week_ago = datetime.now() - timedelta(days=7)

    async with async_session() as session:
        # Всего зарегистрированных
        total_result = await session.execute(
            select(sa_func.count(User.id))
        )
        total_users = total_result.scalar() or 0

        # Активных за неделю (есть last_active_at >= week_ago)
        active_result = await session.execute(
            select(sa_func.count(User.id))
            .where(User.last_active_at >= week_ago)
        )
        active_users = active_result.scalar() or 0

        # С заполненным профилем
        profile_result = await session.execute(
            select(sa_func.count(User.id))
            .where(User.daily_calorie_target.isnot(None))
        )
        profile_users = profile_result.scalar() or 0

        # Новых за неделю
        new_result = await session.execute(
            select(sa_func.count(User.id))
            .where(User.created_at >= week_ago)
        )
        new_users = new_result.scalar() or 0

    text = (
        "👥 <b>Статистика пользователей</b>\n\n"
        f"Всего зарегистрировано: <b>{total_users}</b>\n"
        f"С заполненным профилем: <b>{profile_users}</b>\n"
        f"Активных за неделю: <b>{active_users}</b>\n"
        f"Новых за неделю: <b>{new_users}</b>\n\n"
        "<i>Активность определяется по последнему взаимодействию с ботом</i>"
    )

    await message.answer(text)
