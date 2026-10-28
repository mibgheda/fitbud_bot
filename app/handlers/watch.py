"""
⌚ Часы Apple Watch: подключение команды iPhone, уведомления о тренировках с часов,
вопрос «это одна тренировка?» при похожей записи текстом.
"""
import logging
import os
from html import escape

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database.database import WorkoutEntry
from utils import diary, health, nutrition
from utils.daytime import to_local

logger = logging.getLogger(__name__)
router = Router()

SHORTCUT_URL = os.getenv('HEALTH_SHORTCUT_URL', '')


def _menu_keyboard(connected: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔑 Новый ключ" if connected else "🔑 Получить ключ",
                                  callback_data="watch:key")]]
    if connected:
        rows.append([InlineKeyboardButton(text="❌ Отключить часы", callback_data="watch:off")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "watch:menu")
async def watch_menu(callback: CallbackQuery):
    await callback.answer()
    device = await health.active_device(callback.from_user.id)
    if device:
        user = await diary.get_user(callback.from_user.id)
        last = (to_local(device.last_sync_at, user).strftime('%d.%m в %H:%M')
                if device.last_sync_at else "ещё не было")
        text = (
            "⌚ <b>Часы подключены</b>\n\n"
            f"Последняя отправка данных: <b>{last}</b>\n\n"
            "Данные приходят, когда открываешь Telegram, и 3 раза в день по расписанию."
        )
    else:
        text = (
            "⌚ <b>Подключить Apple Watch</b>\n\n"
            "Шаги, тренировки, пульс и сон из приложения «Здоровье» будут сами попадать в дневник, "
            "а активность с часов — в норму калорий.\n\n"
            "Нужен iPhone. Нажми «Получить ключ» — пришлю ключ и ссылку на команду."
        )
    await callback.message.answer(text, reply_markup=_menu_keyboard(bool(device)))


@router.callback_query(F.data == "watch:key")
async def watch_key(callback: CallbackQuery):
    await callback.answer()
    token = await health.issue_token(callback.from_user.id)
    link = (f'<a href="{SHORTCUT_URL}">Установить команду FitBud</a>' if SHORTCUT_URL
            else "<i>ссылка на команду появится позже</i>")
    await callback.message.answer(
        "🔑 <b>Твой ключ для часов</b> (нажми, чтобы скопировать):\n\n"
        f"<code>{token}</code>\n\n"
        "<b>Как подключить:</b>\n"
        f"1. {link}\n"
        "2. При установке команда попросит ключ — вставь его.\n"
        "3. В «Командах» → «Автоматизация» добавь запуск команды при открытии Telegram "
        "и в 13:00, 18:00 и 22:00, режим «Выполнять сразу».\n\n"
        "Старый ключ, если был, больше не работает. Никому не пересылай этот ключ.",
        disable_web_page_preview=True
    )


@router.callback_query(F.data == "watch:off")
async def watch_off(callback: CallbackQuery):
    await callback.answer()
    await health.revoke_tokens(callback.from_user.id)
    await callback.message.answer(
        "❌ Часы отключены: ключ больше не работает. Уже полученные данные остались в дневнике.\n"
        "Удали команду FitBud на iPhone, чтобы она не пыталась отправлять данные."
    )


# ==================== Новые тренировки и дубли ====================

def _workout_text(entry: WorkoutEntry, user) -> str:
    if entry.source_type == 'watch' and entry.started_at and entry.ended_at:
        when = f"часы, {to_local(entry.started_at, user):%H:%M}–{to_local(entry.ended_at, user):%H:%M}"
        icon = "⌚"
    else:
        when = f"записано в {to_local(entry.created_at, user):%H:%M}"
        icon = "✍️"
    return f"{icon} {escape(entry.workout_type)} {entry.duration} мин · {entry.calories_burned} ккал ({when})"


async def ask_duplicate(bot, user, watch_entry: WorkoutEntry, manual_entry: WorkoutEntry):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одна, оставить с часов",
                             callback_data=f"wd:keep:{watch_entry.id}:{manual_entry.id}"),
        InlineKeyboardButton(text="➕ Это разные", callback_data="wd:both"),
    ]])
    await bot.send_message(
        user.telegram_id,
        "🤔 <b>Похоже, это одна и та же тренировка:</b>\n\n"
        f"{_workout_text(watch_entry, user)}\n{_workout_text(manual_entry, user)}",
        reply_markup=keyboard
    )


async def notify_new_workouts(bot, user, workouts):
    """Сообщить о тренировках, пришедших с часов, и спросить про похожие записи"""
    for entry in workouts:
        try:
            await bot.send_message(
                user.telegram_id,
                f"⌚ <b>Тренировка с часов:</b> {escape(entry.workout_type)}, {entry.duration} мин · "
                f"{entry.calories_burned} ккал" + (f" · {nutrition.fmt(round(entry.distance, 1))} км"
                                                   if entry.distance else "")
            )
            duplicate = await health.find_duplicate(entry)
            if duplicate:
                await ask_duplicate(bot, user, entry, duplicate)
        except Exception:
            logger.exception("Не удалось отправить уведомление о тренировке")


async def check_manual_workout(bot, user, entry_id: int):
    """После записи тренировки текстом: нет ли такой же с часов"""
    entry = await diary.get_entry('w', entry_id, user.telegram_id)
    if not entry:
        return
    duplicate = await health.find_duplicate(entry)
    if duplicate:
        await ask_duplicate(bot, user, duplicate, entry)


@router.callback_query(F.data.startswith("wd:"))
async def resolve_duplicate(callback: CallbackQuery):
    parts = callback.data.split(":")
    if parts[1] == 'keep':
        manual_id = int(parts[3])
        removed = await diary.set_deleted('w', manual_id, callback.from_user.id, deleted=True)
        await callback.answer("Оставил тренировку с часов" if removed else "Уже обработано")
        await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Оставил тренировку с часов.</b>")
    else:
        await callback.answer("Оставил обе")
        await callback.message.edit_text(callback.message.html_text + "\n\n➕ <b>Оставил обе тренировки.</b>")
