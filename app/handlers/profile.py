from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from database.database import async_session, User
from keyboards.reply import get_main_menu

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

        activity_text = {
            'sedentary': 'Минимальный',
            'light': 'Легкий',
            'moderate': 'Средний',
            'active': 'Высокий',
            'very_active': 'Экстремальный'
        }

        goal_text = {
            'lose_weight': 'Похудение 📉',
            'maintain': 'Поддержание веса ➡️',
            'gain_weight': 'Набор массы 📈'
        }

        profile_text = (
            f"👤 <b>Твой профиль</b>\n\n"
            f"Имя: <b>{user.full_name or 'Не указано'}</b>\n"
            f"Возраст: <b>{user.age}</b> лет\n"
            f"Пол: <b>{gender_text}</b>\n"
            f"Рост: <b>{user.height}</b> см\n"
            f"Вес: <b>{user.weight}</b> кг\n\n"
            f"{bmi_emoji} ИМТ: <b>{bmi:.1f}</b> ({bmi_category})\n\n"
            f"Активность: <b>{activity_text.get(user.activity_level, 'Не указано')}</b>\n"
            f"Цель: <b>{goal_text.get(user.goal, 'Не указана')}</b>\n\n"
            f"🎯 Целевая калорийность: <b>{user.daily_calorie_target}</b> ккал/день\n\n"
            f"<i>Для изменения профиля используй /start</i>"
        )

        await message.answer(profile_text, reply_markup=get_main_menu())
