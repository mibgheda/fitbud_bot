"""
Настройки пользователя: часовой пояс, время утра, своя норма белка.

Используются в трёх сценариях (поле flow в данных FSM):
- onboarding — последние шаги знакомства, затем сохранение профиля;
- migration — разовое обновление для пользователей, зарегистрированных до этой версии:
  пояс, утро и активность вне тренировок (раньше норма уже включала тренировки);
- profile — изменение одной настройки из «👤 Мой профиль».
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.database import async_session, User
from sqlalchemy import select
from keyboards.reply import (
    get_main_menu, get_timezone_keyboard, get_wake_keyboard,
    get_activity_level_keyboard, not_menu_button,
)
from utils import nutrition
from utils.daytime import TIMEZONES, format_offset, parse_offset_input, utc_now, DAY_START_BEFORE_WAKE
from datetime import timedelta

logger = logging.getLogger(__name__)
router = Router()


class SettingsFlow(StatesGroup):
    tz = State()
    tz_custom = State()
    wake = State()
    activity = State()
    protein = State()


TZ_QUESTION = (
    "🕐 <b>Какой у тебя часовой пояс?</b>\n\n"
    "Telegram не сообщает мне твоё время, а без него «сегодня» будет начинаться не в полночь."
)

WAKE_QUESTION = (
    "🌅 <b>Во сколько у тебя обычно начинается утро?</b>\n\n"
    f"День в дневнике начнётся за {DAY_START_BEFORE_WAKE} часа до этого времени: "
    "если утро в 7:00, всё съеденное до 4:00 ночи засчитается во вчерашний день."
)


async def _save_user(telegram_id: int, **fields) -> User:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()
        for key, value in fields.items():
            setattr(user, key, value)
        await session.commit()
        return user


async def ask_timezone(message: Message, state: FSMContext, flow: str):
    await send_timezone_question(message.bot, message.chat.id, state, flow)


async def send_timezone_question(bot, chat_id: int, state: FSMContext, flow: str):
    await state.update_data(flow=flow)
    await state.set_state(SettingsFlow.tz)
    await bot.send_message(chat_id, TZ_QUESTION, reply_markup=get_timezone_keyboard())


def needs_migration(user) -> bool:
    """Профиль из версии без часового пояса и времени утра"""
    return bool(user and user.daily_calorie_target and (user.utc_offset_min is None or user.wake_hour is None))


async def send_migration(bot, chat_id: int, state: FSMContext, pending_text: str = None):
    """
    Разовое обновление профиля для пользователей старой версии (запускает middlewares.UpdateGate).
    pending_text — сообщение, с которым пользователь пришёл: разберём его после трёх вопросов.
    """
    await state.clear()
    if pending_text:
        await state.update_data(after_migration_text=pending_text)
    await bot.send_message(
        chat_id,
        "✨ <b>Я обновился!</b>\n\n"
        "Теперь я считаю белки, жиры, углеводы, клетчатку, сахар и жидкость, "
        "учитываю тренировки и твоё местное время.\n\n"
        "Ответь на 3 коротких вопроса — и можно продолжать."
        + ("\n\n<i>Твоё сообщение я запомнил и разберу сразу после.</i>" if pending_text else "")
    )
    await send_timezone_question(bot, chat_id, state, 'migration')


def _local_time_text(offset: int) -> str:
    return (utc_now() + timedelta(minutes=offset)).strftime('%H:%M')


async def _after_timezone(message: Message, state: FSMContext, offset: int, label: str):
    data = await state.get_data()
    flow = data.get('flow')
    offset_text = format_offset(offset)
    shown = label if label == offset_text else f"{label} ({offset_text})"
    confirm = f"✅ Часовой пояс: <b>{shown}</b>, у тебя сейчас {_local_time_text(offset)}."
    if flow == 'profile':
        await _save_user(message.chat.id, utc_offset_min=offset, tz_label=label)
        await state.clear()
        await message.answer(confirm, reply_markup=get_main_menu())
        return
    if flow == 'migration':
        await _save_user(message.chat.id, utc_offset_min=offset, tz_label=label)
    else:
        await state.update_data(utc_offset_min=offset, tz_label=label)
    await message.answer(confirm)
    await state.set_state(SettingsFlow.wake)
    await message.answer(WAKE_QUESTION, reply_markup=get_wake_keyboard())


@router.callback_query(SettingsFlow.tz, F.data.startswith("tz:"))
async def process_timezone(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    await callback.answer()
    if value == 'custom':
        await state.set_state(SettingsFlow.tz_custom)
        await callback.message.edit_text(
            "🌍 Напиши, <b>сколько у тебя сейчас времени</b>, например <i>14:35</i>.\n"
            "Или смещение от UTC: <i>+3</i>, <i>UTC+5:30</i>."
        )
        return
    offset = int(value)
    label = next((name for name, minutes in TIMEZONES if minutes == offset), format_offset(offset))
    await callback.message.edit_reply_markup(reply_markup=None)
    await _after_timezone(callback.message, state, offset, label)


@router.message(SettingsFlow.tz_custom, not_menu_button)
async def process_timezone_custom(message: Message, state: FSMContext):
    offset = parse_offset_input(message.text)
    if offset is None:
        await message.answer("Не понял 🤔 Напиши время в формате <i>14:35</i> или смещение, например <i>+3</i>.")
        return
    await _after_timezone(message, state, offset, format_offset(offset))


@router.callback_query(SettingsFlow.wake, F.data.startswith("wake:"))
async def process_wake(callback: CallbackQuery, state: FSMContext):
    wake = int(callback.data.split(":", 1)[1])
    await callback.answer()
    data = await state.get_data()
    flow = data.get('flow')
    start_hour = max(0, wake - DAY_START_BEFORE_WAKE)
    await callback.message.edit_text(f"✅ Утро в <b>{wake}:00</b>, новый день начинается в {start_hour}:00.")

    if flow == 'profile':
        await _save_user(callback.from_user.id, wake_hour=wake)
        await state.clear()
        await callback.message.answer("Готово!", reply_markup=get_main_menu())
    elif flow == 'migration':
        await _save_user(callback.from_user.id, wake_hour=wake)
        await state.set_state(SettingsFlow.activity)
        await callback.message.answer(
            "🚶 <b>Какая у тебя активность вне тренировок?</b>\n\n"
            "Тренировки теперь считаются отдельно и прибавляются к норме калорий "
            "в тот день, когда ты их записываешь.",
            reply_markup=get_activity_level_keyboard()
        )
    else:
        await state.update_data(wake_hour=wake)
        await finish_onboarding(callback.message, state, callback.from_user.id)


@router.callback_query(SettingsFlow.activity, F.data.startswith("activity_"))
async def process_migration_activity(callback: CallbackQuery, state: FSMContext):
    activity = callback.data.split("_", 1)[1]
    await callback.answer()
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one()
        user.activity_level = activity
        user.daily_calorie_target = nutrition.calculate_calories(
            user.gender, user.weight, user.height, user.age, activity, user.goal or 'maintain'
        )
        await session.commit()
    pending_text = (await state.get_data()).get('after_migration_text')
    await state.clear()
    await callback.message.edit_text(
        f"✅ Активность: <b>{nutrition.ACTIVITY_LABELS[activity]}</b>\n\n"
        f"<b>Твои новые нормы:</b>\n{nutrition.norms_text(nutrition.daily_norms(user))}\n\n"
        + ("Всё готово! Разбираю твоё сообщение..." if pending_text
           else "Всё готово! Пиши, что съел(а) или как тренировался(лась), присылай фото или голосовое.")
    )
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu())
    if pending_text:
        # Импорт здесь: ai_hub сам импортирует этот модуль
        from handlers.ai_hub import run_analysis
        await run_analysis(callback.message, state, user, pending_text, 'text')


async def finish_onboarding(message: Message, state: FSMContext, telegram_id: int):
    """Сохранить профиль после знакомства и показать нормы"""
    data = await state.get_data()
    target = nutrition.calculate_calories(
        data['gender'], data['weight'], data['height'], data['age'], data['activity_level'], data['goal']
    )
    user = await _save_user(
        telegram_id,
        full_name=data.get('name'),
        age=data['age'],
        gender=data['gender'],
        height=data['height'],
        weight=data['weight'],
        activity_level=data['activity_level'],
        goal=data['goal'],
        daily_calorie_target=target,
        utc_offset_min=data['utc_offset_min'],
        tz_label=data['tz_label'],
        wake_hour=data['wake_hour'],
    )
    await state.clear()
    await message.answer(
        f"🎉 <b>{data.get('name', 'Друг')}, профиль настроен!</b>\n\n"
        f"Цель: <b>{nutrition.GOAL_LABELS[data['goal']]}</b>\n"
        f"Активность вне тренировок: <b>{nutrition.ACTIVITY_LABELS[data['activity_level']]}</b>\n\n"
        f"<b>Твои нормы на день:</b>\n{nutrition.norms_text(nutrition.daily_norms(user))}\n\n"
        "Главное — <b>добрать белки и клетчатку</b> и не перебрать жиры, углеводы и сахар.\n\n"
        "Просто напиши, что съел(а), пришли фото еды или голосовое 💪",
        reply_markup=get_main_menu()
    )


# ==================== Из профиля ====================

@router.callback_query(F.data == "set:tz")
async def profile_timezone(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await ask_timezone(callback.message, state, 'profile')


@router.callback_query(F.data == "set:wake")
async def profile_wake(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.update_data(flow='profile')
    await state.set_state(SettingsFlow.wake)
    await callback.message.answer(WAKE_QUESTION, reply_markup=get_wake_keyboard())


@router.callback_query(F.data == "set:protein")
async def profile_protein(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(SettingsFlow.protein)
    low, high = nutrition.PROTEIN_PER_KG_RANGE
    await callback.message.answer(
        "🥩 <b>Своя норма белка</b>\n\n"
        "По умолчанию: похудение и набор — 1,8 г на кг веса, поддержание — 1,4 г/кг.\n\n"
        f"Напиши свою норму в граммах на кг (от {low:g} до {high:g}), например <i>2,2</i>.\n"
        "Чтобы вернуть норму по цели, напиши <i>по цели</i>."
    )


@router.message(SettingsFlow.protein, not_menu_button)
async def process_protein(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    low, high = nutrition.PROTEIN_PER_KG_RANGE
    if text in ('по цели', 'сброс', 'по умолчанию'):
        value = None
    else:
        try:
            value = float(text.replace(',', '.').replace('г/кг', '').strip())
        except ValueError:
            await message.answer(f"Напиши число от {low:g} до {high:g}, например <i>2,2</i>.")
            return
        if not low <= value <= high:
            await message.answer(f"Норма должна быть от {low:g} до {high:g} г на кг.")
            return
    user = await _save_user(message.from_user.id, protein_per_kg=value)
    await state.clear()
    norms = nutrition.daily_norms(user)
    per_kg = nutrition.protein_per_kg(user)
    await message.answer(
        f"✅ Норма белка: <b>{nutrition.fmt(per_kg)} г/кг</b> → <b>от {norms['protein']} г</b> в день"
        + (" (по цели)" if value is None else ""),
        reply_markup=get_main_menu()
    )
