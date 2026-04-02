from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


# Тексты кнопок главного меню — используется для фильтрации в FSM-хэндлерах
MENU_BUTTONS = [
    "✨ Быстрый ввод",
    "💧 Вода",
    # "🍽 План питания", "🏋️ План тренировок",  # Отложено на этап 2, не удалять!
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
        [KeyboardButton(text="✨ Быстрый ввод"), KeyboardButton(text="💧 Вода")],
        # [KeyboardButton(text="🍽 План питания"), KeyboardButton(text="🏋️ План тренировок")],  # Отложено на этап 2, не удалять!
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


DAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']


def get_meal_plan_day_keyboard(plan_id: int, current_day: int, items: list):
    """Клавиатура навигации плана питания на день"""
    keyboard = []

    # Кнопки для каждого приёма пищи: рецепт + выполнено
    meal_emoji = {'breakfast': '🌅', 'lunch': '🌞', 'dinner': '🌙', 'snack': '🍎'}
    for item in items:
        row = []
        emoji = meal_emoji.get(item.meal_type, '🍽')
        if item.is_completed:
            row.append(InlineKeyboardButton(
                text=f"✅ {emoji} Выполнено",
                callback_data=f"_"  # noop
            ))
        else:
            row.append(InlineKeyboardButton(
                text=f"📖 Рецепт",
                callback_data=f"mpr_{item.id}"
            ))
            row.append(InlineKeyboardButton(
                text=f"✅ Съел",
                callback_data=f"mpc_{item.id}"
            ))
        keyboard.append(row)

    # Навигация по дням
    nav_row = []
    if current_day > 0:
        nav_row.append(InlineKeyboardButton(
            text=f"← {DAY_NAMES[current_day - 1]}",
            callback_data=f"mpd_{plan_id}_{current_day - 1}"
        ))
    nav_row.append(InlineKeyboardButton(
        text=f"· {DAY_NAMES[current_day]} ·",
        callback_data="_"
    ))
    if current_day < 6:
        nav_row.append(InlineKeyboardButton(
            text=f"{DAY_NAMES[current_day + 1]} →",
            callback_data=f"mpd_{plan_id}_{current_day + 1}"
        ))
    keyboard.append(nav_row)

    # Новый план
    keyboard.append([InlineKeyboardButton(text="🔄 Новый план", callback_data="mpn")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_workout_plan_day_keyboard(plan_id: int, current_day: int, item=None):
    """Клавиатура навигации плана тренировок на день"""
    keyboard = []

    # Кнопка выполнения
    if item and not item.is_rest_day:
        if item.is_completed:
            keyboard.append([InlineKeyboardButton(
                text="✅ Тренировка выполнена",
                callback_data="_"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                text="✅ Отметить выполненной",
                callback_data=f"wpc_{item.id}"
            )])

    # Навигация по дням
    nav_row = []
    if current_day > 0:
        nav_row.append(InlineKeyboardButton(
            text=f"← {DAY_NAMES[current_day - 1]}",
            callback_data=f"wpd_{plan_id}_{current_day - 1}"
        ))
    nav_row.append(InlineKeyboardButton(
        text=f"· {DAY_NAMES[current_day]} ·",
        callback_data="_"
    ))
    if current_day < 6:
        nav_row.append(InlineKeyboardButton(
            text=f"{DAY_NAMES[current_day + 1]} →",
            callback_data=f"wpd_{plan_id}_{current_day + 1}"
        ))
    keyboard.append(nav_row)

    # Новый план
    keyboard.append([InlineKeyboardButton(text="🔄 Новый план", callback_data="wpn")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_confirm_keyboard():
    """Клавиатура подтверждения удаления аккаунта"""
    keyboard = [
        [InlineKeyboardButton(text="🗑 Да, удалить все данные", callback_data="confirm_delete_account")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_account")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
