from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


# Тексты кнопок главного меню — используется для фильтрации в FSM-хэндлерах
MENU_BUTTONS = [
    "✨ Быстрый ввод",
    "💧 Вода",
    "📋 Мой день",
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
        [KeyboardButton(text="📋 Мой день"), KeyboardButton(text="📈 Моя статистика")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="⚖️ Записать вес")],
        [KeyboardButton(text="❓ Помощь")]
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
    """Клавиатура выбора активности вне тренировок (тренировки считаются отдельно)"""
    keyboard = [
        [InlineKeyboardButton(text="🪑 Сидячая работа", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Много хожу, на ногах", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏗 Физический труд", callback_data="activity_moderate")]
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


def get_ai_confirm_keyboard(editing: bool = False):
    """Подтверждение распознанного AI (еда и/или тренировки)"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Сохранить" if editing else "✅ Добавить", callback_data="ai_confirm"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data="ai_edit")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ai_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_saved_entries_keyboard(entries: list):
    """Кнопки под сохранённой записью: [(kind, id, подпись), ...]; kind — f (еда) или w (тренировка)"""
    keyboard = []
    for kind, entry_id, label in entries:
        suffix = f" {label}" if len(entries) > 1 else ""
        keyboard.append([
            InlineKeyboardButton(text=f"✏️ Исправить{suffix}", callback_data=f"ee:{kind}:{entry_id}"),
            InlineKeyboardButton(text=f"🗑 Удалить{suffix}", callback_data=f"ed:{kind}:{entry_id}")
        ])
    keyboard.append([InlineKeyboardButton(text="📋 Мой день", callback_data="day:0")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_undo_keyboard(kind: str, entry_id: int):
    keyboard = [[InlineKeyboardButton(text="↩️ Отменить удаление", callback_data=f"eu:{kind}:{entry_id}")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_day_keyboard(days_ago: int, buttons: list, max_days_back: int):
    """Список записей дня: кнопки с номерами + навигация по дням. buttons — [(номер, kind, id)]"""
    keyboard = []
    row = []
    for number, kind, entry_id in buttons:
        row.append(InlineKeyboardButton(text=str(number), callback_data=f"ev:{kind}:{entry_id}:{days_ago}"))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    nav = []
    if days_ago < max_days_back:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"day:{days_ago + 1}"))
    if days_ago > 0:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"day:{days_ago - 1}"))
    if nav:
        keyboard.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_entry_keyboard(kind: str, entry_id: int, days_ago: int):
    keyboard = [
        [
            InlineKeyboardButton(text="✏️ Исправить", callback_data=f"ee:{kind}:{entry_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ed:{kind}:{entry_id}")
        ],
        [InlineKeyboardButton(text="◀️ К списку", callback_data=f"day:{days_ago}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_water_keyboard():
    """Быстрый ввод воды"""
    keyboard = [[
        InlineKeyboardButton(text=f"{ml} мл", callback_data=f"water:{ml}") for ml in (150, 250, 330, 500)
    ]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_timezone_keyboard():
    """Выбор часового пояса"""
    from utils.daytime import TIMEZONES, format_offset
    keyboard = []
    row = []
    for label, offset in TIMEZONES:
        row.append(InlineKeyboardButton(text=f"{label} ({format_offset(offset)})", callback_data=f"tz:{offset}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="🌍 Другой — введу своё время", callback_data="tz:custom")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_wake_keyboard():
    """Во сколько у пользователя утро"""
    from utils.daytime import WAKE_HOURS
    row1 = [InlineKeyboardButton(text=f"{h}:00", callback_data=f"wake:{h}") for h in WAKE_HOURS[:4]]
    row2 = [InlineKeyboardButton(text=f"{h}:00", callback_data=f"wake:{h}") for h in WAKE_HOURS[4:]]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


def get_profile_settings_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="🕐 Часовой пояс", callback_data="set:tz"),
         InlineKeyboardButton(text="🌅 Время утра", callback_data="set:wake")],
        [InlineKeyboardButton(text="🥩 Своя норма белка", callback_data="set:protein")],
        [InlineKeyboardButton(text="🔄 Заполнить профиль заново", callback_data="set:restart")]
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
