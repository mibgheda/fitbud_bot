from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from html import escape
from sqlalchemy import select

from database.database import async_session, User
from keyboards.reply import get_main_menu, get_profile_settings_keyboard
from utils import nutrition
from utils.daytime import format_offset, day_start_hour, DEFAULT_WAKE_HOUR

router = Router()


@router.message(F.text == "👤 Мой профиль")
@router.message(Command("profile"))
async def show_profile(message: Message, state: FSMContext):
    """Показать профиль пользователя"""
    await state.clear()
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.age:
            await message.answer(
                "У тебя еще не настроен профиль.\n"
                "Используй команду /start для настройки!",
                reply_markup=get_main_menu()
            )
            return

        # Рассчитываем ИМТ
        height_m = user.height / 100
        bmi = user.weight / (height_m ** 2)

        # Определяем категорию ИМТ
        if bmi < 18.5:
            bmi_category = "Недостаточный вес"
            bmi_emoji = "⚠️"
        elif 18.5 <= bmi < 25:
            bmi_category = "Нормальный вес"
            bmi_emoji = "✅"
        elif 25 <= bmi < 30:
            bmi_category = "Избыточный вес"
            bmi_emoji = "⚠️"
        else:
            bmi_category = "Ожирение"
            bmi_emoji = "❗"

        gender_text = "Мужской" if user.gender == "male" else "Женский"

        norms = nutrition.daily_norms(user)
        per_kg = nutrition.protein_per_kg(user)
        protein_note = "своя норма" if user.protein_per_kg else "по цели"
        tz_text = "не указан"
        if user.utc_offset_min is not None:
            offset_text = format_offset(user.utc_offset_min)
            tz_text = offset_text if user.tz_label in (None, offset_text) else f"{user.tz_label} ({offset_text})"
        wake = user.wake_hour if user.wake_hour is not None else DEFAULT_WAKE_HOUR

        profile_text = (
            f"👤 <b>Твой профиль</b>\n\n"
            f"Имя: <b>{escape(user.full_name or 'Не указано')}</b>\n"
            f"Возраст: <b>{user.age}</b> лет\n"
            f"Пол: <b>{gender_text}</b>\n"
            f"Рост: <b>{user.height}</b> см\n"
            f"Вес: <b>{nutrition.fmt(user.weight)}</b> кг\n\n"
            f"{bmi_emoji} ИМТ: <b>{nutrition.fmt(round(bmi, 1))}</b> ({bmi_category})\n\n"
            f"Активность вне тренировок: <b>{nutrition.ACTIVITY_LABELS.get(user.activity_level, 'Физический труд')}</b>\n"
            f"Цель: <b>{nutrition.GOAL_LABELS.get(user.goal, 'Не указана')}</b>\n"
            f"Белок: <b>{nutrition.fmt(per_kg)} г/кг</b> ({protein_note})\n\n"
            f"🕐 Часовой пояс: <b>{tz_text}</b>\n"
            f"🌅 Утро: <b>{wake}:00</b> (новый день с {day_start_hour(user)}:00)\n\n"
            f"<b>Нормы на день:</b>\n{nutrition.norms_text(norms)}"
        )

        await message.answer(profile_text, reply_markup=get_profile_settings_keyboard())
