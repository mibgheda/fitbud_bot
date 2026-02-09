from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu():
    """Главное меню бота"""
    keyboard = [
        [KeyboardButton(text="📊 Добавить калории"), KeyboardButton(text="🏃 Добавить тренировку")],
        [KeyboardButton(text="📈 Моя статистика"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚖️ Записать вес"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_meal_type_keyboard():
    """Клавиатура выбора типа приема пищи"""
    keyboard = [
        [InlineKeyboardButton(text="🌅 Завтрак", callback_data="meal_breakfast")],
        [InlineKeyboardButton(text="🌞 Обед", callback_data="meal_lunch")],
        [InlineKeyboardButton(text="🌙 Ужин", callback_data="meal_dinner")],
        [InlineKeyboardButton(text="🍎 Перекус", callback_data="meal_snack")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_workout_type_keyboard():
    """Клавиатура выбора типа тренировки"""
    keyboard = [
        [InlineKeyboardButton(text="🏃 Бег", callback_data="workout_running")],
        [InlineKeyboardButton(text="🏋️ Тренажерный зал", callback_data="workout_gym")],
        [InlineKeyboardButton(text="🚴 Велосипед", callback_data="workout_cycling")],
        [InlineKeyboardButton(text="🧘 Йога", callback_data="workout_yoga")],
        [InlineKeyboardButton(text="🏊 Плавание", callback_data="workout_swimming")],
        [InlineKeyboardButton(text="🎾 Другое", callback_data="workout_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_gender_keyboard():
    """Клавиатура выбора пола"""
    keyboard = [
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male")],
        [InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_activity_level_keyboard():
    """Клавиатура выбора уровня активности"""
    keyboard = [
        [InlineKeyboardButton(text="🛋 Сидячий образ жизни", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Легкая активность (1-3 раза/нед)", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏃 Умеренная активность (3-5 раз/нед)", callback_data="activity_moderate")],
        [InlineKeyboardButton(text="💪 Активный образ (6-7 раз/нед)", callback_data="activity_active")],
        [InlineKeyboardButton(text="🏆 Очень активный (спортсмен)", callback_data="activity_very_active")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_goal_keyboard():
    """Клавиатура выбора цели"""
    keyboard = [
        [InlineKeyboardButton(text="📉 Похудеть", callback_data="goal_lose_weight")],
        [InlineKeyboardButton(text="➡️ Поддерживать вес", callback_data="goal_maintain")],
        [InlineKeyboardButton(text="📈 Набрать массу", callback_data="goal_gain_weight")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
