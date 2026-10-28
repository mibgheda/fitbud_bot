"""
«📋 Мой день»: отчёт за день, список записей, исправление и удаление.

Удаление мягкое: 30 секунд под сообщением есть кнопка «↩️ Отменить удаление».
"""
import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from handlers.ai_hub import AIInput, ensure_ready, _safe_edit
from keyboards.reply import (
    get_main_menu, get_day_keyboard, get_entry_keyboard, get_undo_keyboard, get_saved_entries_keyboard,
    not_menu_button,
)
from utils import diary, health
from utils.daytime import day_label

logger = logging.getLogger(__name__)
router = Router()

MAX_DAYS_BACK = 7
UNDO_SECONDS = 30


def _parse(data: str):
    parts = data.split(":")
    return parts[1], int(parts[2]), (int(parts[3]) if len(parts) > 3 else 0)


@router.message(F.text == "📋 Мой день")
async def my_day(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_ready(message, state)
    if not user:
        return
    text, buttons, has_watch = await diary.day_report_text(user, 0)
    await message.answer(text, reply_markup=get_day_keyboard(0, buttons, MAX_DAYS_BACK, has_watch))
    if has_watch:
        _, workouts = await diary.load_day(user, 0)
        report = await health.watch_report(user, 0, workouts, day_label(user, 0))
        if report:
            await message.answer(report)


@router.callback_query(F.data.startswith("day:"))
async def day_navigation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await ensure_ready(callback.message, state, callback.from_user.id)
    if not user:
        return
    days_ago = max(0, min(MAX_DAYS_BACK, int(callback.data.split(":", 1)[1])))
    text, buttons, has_watch = await diary.day_report_text(user, days_ago)
    await _safe_edit(callback.message, text,
                     reply_markup=get_day_keyboard(days_ago, buttons, MAX_DAYS_BACK, has_watch))


@router.callback_query(F.data.startswith("wr:"))
async def watch_day(callback: CallbackQuery, state: FSMContext):
    """⌚ Данные с часов за выбранный день"""
    await callback.answer()
    user = await ensure_ready(callback.message, state, callback.from_user.id)
    if not user:
        return
    days_ago = max(0, min(MAX_DAYS_BACK, int(callback.data.split(":", 1)[1])))
    _, workouts = await diary.load_day(user, days_ago)
    report = await health.watch_report(user, days_ago, workouts, day_label(user, days_ago))
    await callback.message.answer(report or "⌚ За этот день данных с часов нет.")


@router.callback_query(F.data.startswith("ev:"))
async def view_entry(callback: CallbackQuery):
    kind, entry_id, days_ago = _parse(callback.data)
    user = await diary.get_user(callback.from_user.id)
    entry = await diary.get_entry(kind, entry_id, callback.from_user.id)
    if not user or not entry:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await callback.answer()
    await _safe_edit(callback.message, diary.entry_details(kind, entry, user),
                     reply_markup=get_entry_keyboard(kind, entry_id, days_ago))


@router.callback_query(F.data.startswith("ee:"))
async def edit_entry(callback: CallbackQuery, state: FSMContext):
    """Исправить сохранённую запись: быстрая правка числа или новое описание для AI"""
    kind, entry_id, _ = _parse(callback.data)
    entry = await diary.get_entry(kind, entry_id, callback.from_user.id)
    if not entry:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await callback.answer()
    await state.clear()
    await state.update_data(
        pending={
            'result': diary.previous_result(kind, entry),
            'input_type': 'text',
            'text': None,
            'interaction_id': None,
            'editing': {'kind': kind, 'id': entry_id},
        },
        quick_edit={'kind': kind, 'id': entry_id},
    )
    await state.set_state(AIInput.waiting_for_edit)
    if kind == 'f':
        hint = ("Напиши, что было на самом деле: <i>«там было 2 котлеты»</i>, <i>«без хлеба»</i>.\n"
                "Или поправь число: <i>«калории 400»</i>, <i>«белки 30»</i>.")
    else:
        hint = ("Напиши, как было на самом деле: <i>«бег 40 минут»</i>, <i>«это была ходьба»</i>.\n"
                "Или поправь время: <i>«45 минут»</i>.")
    await callback.message.answer(f"✏️ <b>Исправляем:</b> {diary.entry_title(kind, entry)}\n\n{hint}")


@router.message(AIInput.waiting_for_edit, not_menu_button)
async def quick_edit_or_ai(message: Message, state: FSMContext):
    """Быстрая правка числа без AI; всё остальное — уточнение через AI (handlers/ai_hub.py)"""
    data = await state.get_data()
    target = data.get('quick_edit')
    fields = diary.parse_quick_edit(message.text) if target else {}
    if not fields:
        from handlers.ai_hub import process_correction
        await process_correction(message, state)
        return
    user = await diary.get_user(message.from_user.id)
    if not await diary.apply_quick_edit(target['kind'], target['id'], user, fields):
        await message.answer("Не получилось применить правку — проверь число.")
        return
    await state.clear()
    entry = await diary.get_entry(target['kind'], target['id'], message.from_user.id)
    await message.answer(
        f"✅ <b>Исправлено!</b>\n\n{diary.entry_details(target['kind'], entry, user)}\n\n"
        f"{await diary.day_brief_text(user)}",
        reply_markup=get_saved_entries_keyboard([(target['kind'], target['id'], '')])
    )


async def _drop_undo_button(message: Message, kind: str, entry_id: int, user_id: int):
    """Через 30 секунд убрать кнопку отмены, если удаление не отменили"""
    await asyncio.sleep(UNDO_SECONDS)
    entry = await diary.get_entry(kind, entry_id, user_id, include_deleted=True)
    if entry and entry.deleted_at:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("ed:"))
async def delete_entry(callback: CallbackQuery):
    kind, entry_id, _ = _parse(callback.data)
    entry = await diary.set_deleted(kind, entry_id, callback.from_user.id, deleted=True)
    if not entry:
        await callback.answer("Запись уже удалена", show_alert=True)
        return
    await callback.answer("Удалено")
    await _safe_edit(callback.message, f"🗑 <b>Удалено:</b> {diary.entry_title(kind, entry)}",
                     reply_markup=get_undo_keyboard(kind, entry_id))
    asyncio.create_task(_drop_undo_button(callback.message, kind, entry_id, callback.from_user.id))


@router.callback_query(F.data.startswith("eu:"))
async def undo_delete(callback: CallbackQuery):
    kind, entry_id, _ = _parse(callback.data)
    entry = await diary.set_deleted(kind, entry_id, callback.from_user.id, deleted=False)
    if not entry:
        await callback.answer("Отменить уже нельзя", show_alert=True)
        return
    await callback.answer("Восстановлено")
    user = await diary.get_user(callback.from_user.id)
    await _safe_edit(
        callback.message,
        f"↩️ <b>Восстановлено:</b> {diary.entry_title(kind, entry)}\n\n{await diary.day_brief_text(user)}",
        reply_markup=get_saved_entries_keyboard([(kind, entry_id, '')])
    )
