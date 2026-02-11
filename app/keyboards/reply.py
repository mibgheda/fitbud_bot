from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


# Тексты кнопок главного меню — используется для фильтрации в FSM-хэндлерах
MENU_BUTTONS = [
    "✨ Быстрый ввод",
    "📈 Моя статистика", "👤 Мой профиль",
    "⚖️ Записать вес", "❓ Помощь"
]


def is_menu_button(message) -> bool:
    """Фильтр: сообщение является кнопкой меню"""
    return message.text in MENU_BUTTONS if message.text else False


def not_menu_button(message) -> bool:
    """Фильтр: сообщение является текстовым И НЕ является кнопкой меню"""
    if not message.text:
        return False
    return message.text not in MENU_BUTTONS


def get_main_menu():
    """Главное меню бота"""
    keyboard = [
        [KeyboardButton(text="✨ Быстрый ввод")],
        [KeyboardButton(text="📈 Моя статистика"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="⚖️ Записать вес"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_agreement_keyboard():
    """Клавиатура принятия пользовательского соглашения и политики ПДн"""
    keyboard = [
        [InlineKeyboardButton(
            text="📋 Пользовательское соглашение",
            url="https://telegra.ph/Polzovatelskoe-soglashenie-dlya-Telegram-bota-FitBud-02-09"
        )],
        [InlineKeyboardButton(
            text="🔒 Политика обработки ПДн",
            url="https://telegra.ph/Politika-obrabotki-personalnyh-dannyh-v-ramkah-Telegram-bota-FitBud-02-09"
        )],
        [InlineKeyboardButton(text="✅ Я принимаю условия", callback_data="accept_agreement")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
        [InlineKeyboardButton(text="🛋 Минимальный (сидячий образ жизни)", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Легкий (1-3 раза/нед)", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏃 Средний (3-5 раз/нед)", callback_data="activity_moderate")],
        [InlineKeyboardButton(text="💪 Высокий (6-7 раз/нед)", callback_data="activity_active")],
        [InlineKeyboardButton(text="🏆 Экстремальный (спортсмен)", callback_data="activity_very_active")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_goal_keyboard():
    """Клавиатура выбора цели"""
    keyboard = [
        [InlineKeyboardButton(text="➡️ Поддержание веса", callback_data="goal_maintain")],
        [InlineKeyboardButton(text="📉 Похудение", callback_data="goal_lose_weight")],
        [InlineKeyboardButton(text="📈 Набор массы", callback_data="goal_gain_weight")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_ai_food_confirm_keyboard():
    """Клавиатура подтверждения AI-распознанной еды"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Добавить", callback_data="ai_food_confirm"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="ai_food_edit")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_ai_workout_confirm_keyboard():
    """Клавиатура подтверждения AI-распознанной тренировки"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Добавить", callback_data="ai_workout_confirm"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="ai_workout_edit")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_confirm_keyboard():
    """Клавиатура подтверждения удаления аккаунта"""
    keyboard = [
        [InlineKeyboardButton(text="🗑 Да, удалить все данные", callback_data="confirm_delete_account")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_account")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
