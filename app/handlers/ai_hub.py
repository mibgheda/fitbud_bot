"""
AI-хаб: любое сообщение — текст, голос или фото — разбирает AI.

Тип сообщения (еда, напитки, вода, тренировка) определяет AI, а не список слов.
Результат показывается пользователю, сохраняется после «✅ Добавить».
Защита от prompt injection — в utils/openai_helper.py (analyze_input).
"""
import logging
import os
from datetime import datetime
from html import escape
from typing import Optional

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, Voice, PhotoSize
from sqlalchemy import select

from database.database import async_session, User
from keyboards.reply import (
    get_main_menu, MENU_BUTTONS, not_menu_button,
    get_ai_confirm_keyboard, get_saved_entries_keyboard, get_water_keyboard,
)
from handlers.settings import send_migration, needs_migration
from utils import diary, nutrition
from utils.daytime import local_now, utc_now
from utils.limits import check_limit, log_ai, mark_added, MAX_VOICE_SECONDS
from utils.openai_helper import transcribe_voice, analyze_input, MAX_INPUT_CHARS

logger = logging.getLogger(__name__)
router = Router()

# Директория для временного хранения медиа-файлов (удаляются после анализа)
MEDIA_DIR = "/app/media"
os.makedirs(f"{MEDIA_DIR}/voice", exist_ok=True)
os.makedirs(f"{MEDIA_DIR}/photos", exist_ok=True)


class AIInput(StatesGroup):
    """Состояния AI-ввода"""
    pending_confirmation = State()  # показан результат — ждём «Добавить», «Изменить» или уточнение текстом
    waiting_for_edit = State()  # нажали «Изменить» — ждём описание
    waiting_for_duration = State()  # AI не понял длительность тренировки


NOT_RECOGNIZED_TEXT = (
    "🤔 <b>Не нашёл здесь еды, напитков или тренировки</b>\n\n"
    "Я веду дневник питания и тренировок. Попробуй так:\n\n"
    "🍽 <i>«Борщ с хлебом и котлета»</i>\n"
    "☕ <i>«Капучино и круассан»</i>\n"
    "💧 <i>«Выпила 0,5 л воды»</i>\n"
    "🏃 <i>«Пробежал 5 км за 30 минут»</i>\n\n"
    "Можно прислать фото еды или голосовое."
)


# ==================== Вспомогательные ====================

async def ensure_ready(message: Message, state: FSMContext, user_id: Optional[int] = None) -> Optional[User]:
    """Пользователь с настроенным профилем; иначе — отправить настраивать"""
    user_id = user_id or message.from_user.id
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user or not user.daily_calorie_target:
            await message.answer(
                "Сначала настрой профиль командой /start, чтобы пользоваться дневником.",
                reply_markup=get_main_menu()
            )
            return None
        if needs_migration(user):
            # Обычно сюда не доходит: обновление запускает middlewares.UpdateGate
            await send_migration(message.bot, message.chat.id, state)
            return None
        user.last_active_at = utc_now()
        await session.commit()
        return user


def _user_context(user: User) -> dict:
    return {'local_time': local_now(user).strftime('%H:%M'), 'weight': user.weight}


def _result_summary(result: dict) -> str:
    """Прошлый разбор одной строкой — контекст для уточнения"""
    parts = [f"{item['name']} ({item['calories']} ккал)" for item in result.get('items', [])]
    parts += [f"тренировка: {w['name']}, {w['duration_min']} мин" for w in result.get('workouts', [])]
    return "; ".join(parts) or "ничего"


async def _safe_edit(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


def _preview_text(user: User, result: dict, editing: bool) -> Optional[str]:
    """Текст предпросмотра или None, если данные нереалистичны"""
    norms = nutrition.daily_norms(user)
    lines = ["✏️ <b>Исправленная запись:</b>" if editing else "🤖 <b>Распознано:</b>", ""]

    if result['items']:
        totals = nutrition.meal_totals(result['items'])
        if totals['calories'] > 5000 or totals['protein'] > 300 or totals['fats'] > 300 or totals['carbs'] > 500:
            return None
        for item in result['items']:
            line = f"• {escape(item['name'])} — {item['calories']} ккал"
            if item['liquid_type'] != 'none' and item['liquid_ml']:
                line += f", {item['liquid_ml']} мл"
            lines.append(line)
        lines.append("")
        lines.append(nutrition.meal_report(totals, norms))

    if result['workouts']:
        if result['items']:
            lines.append("")
        weight = user.weight or 70
        for workout in result['workouts']:
            lines.append(f"🏃 <b>{escape(workout['name'])}</b>, {workout['duration_min']} мин"
                         + (f", {nutrition.fmt(workout['distance_km'])} км" if workout['distance_km'] else ""))
            lines.append(f"   🔥 {nutrition.workout_formula(workout['met'], weight, workout['duration_min'])} ккал")

    if result['confidence'] < 0.6:
        lines.append("\n⚠️ <i>Оценка приблизительная — уточни порцию, если знаешь.</i>")
    lines.append("\n<i>Можно уточнить текстом, например: «порция была больше».</i>")
    return "\n".join(lines)


async def show_preview(message: Message, state: FSMContext, user: User):
    data = await state.get_data()
    pending = data['pending']
    text = _preview_text(user, pending['result'], bool(pending.get('editing')))
    if text is None:
        await state.set_state(AIInput.pending_confirmation)
        await message.answer(
            "⚠️ <b>Цифры выглядят нереалистично для одного приёма пищи.</b>\n"
            "Опиши, пожалуйста, ещё раз, что и сколько было."
        )
        return
    await state.set_state(AIInput.pending_confirmation)
    await message.answer(text, reply_markup=get_ai_confirm_keyboard(editing=bool(pending.get('editing'))))


async def _ask_missing_duration(message: Message, state: FSMContext) -> bool:
    """Спросить длительность первой тренировки без неё. True — если спросили"""
    data = await state.get_data()
    for index, workout in enumerate(data['pending']['result']['workouts']):
        if not workout['duration_min']:
            await state.update_data(duration_index=index)
            await state.set_state(AIInput.waiting_for_duration)
            await message.answer(f"⏱ Сколько минут длилась тренировка «{escape(workout['name'])}»? Напиши число.")
            return True
    return False


async def run_analysis(message: Message, state: FSMContext, user: User, text: Optional[str],
                       input_type: str, image_path: Optional[str] = None,
                       check: bool = True, correction: bool = False):
    """Разобрать сообщение через AI и показать результат"""
    if check:
        limit_message = await check_limit(user, input_type)
        if limit_message:
            await message.answer(limit_message, reply_markup=get_main_menu())
            return

    data = await state.get_data()
    pending = data.get('pending') if correction else None
    editing = pending.get('editing') if pending else None

    prompt_text = text
    if pending:
        original = pending.get('text')
        prompt_text = (
            (f"Исходное сообщение: {original}\n" if original else "")
            + f"Предыдущий разбор: {_result_summary(pending['result'])}\n"
            + f"Исправление пользователя: {text}\n"
            + "Верни полный исправленный разбор."
        )

    try:
        result, usage = await analyze_input(prompt_text, image_path, _user_context(user))
    except Exception:
        logger.exception("Ошибка анализа")
        await log_ai(user.telegram_id, 'analysis', input_type, text, status='error')
        await message.answer("❌ Не удалось разобрать сообщение. Попробуй ещё раз чуть позже.")
        return

    interaction_id = await log_ai(user.telegram_id, 'analysis', input_type, text, result, usage)

    if not result['items'] and not result['workouts']:
        if pending:
            await message.answer("🤔 Не понял исправление. Опиши, пожалуйста, иначе — или нажми «✅» под записью.")
        else:
            await message.answer(NOT_RECOGNIZED_TEXT, reply_markup=get_main_menu())
        return

    # Только вода — записываем сразу, без подтверждения
    if not pending and not result['workouts'] and nutrition.is_water_only(result['items']):
        saved = await diary.save_result(user, result, input_type, text, result['confidence'])
        await mark_added(interaction_id, 'calorie_entry', saved[0][1])
        await state.clear()
        ml = sum(item['liquid_ml'] for item in result['items'])
        await message.answer(
            f"✅ <b>Записано: {ml} мл воды</b>\n\n{await diary.liquid_brief_text(user)}",
            reply_markup=get_saved_entries_keyboard(saved)
        )
        return

    await state.update_data(pending={
        'result': result,
        'input_type': input_type,
        'text': (pending.get('text') if pending else None) or (text if not image_path else (text or 'фото')),
        'interaction_id': interaction_id,
        'editing': editing,
    })
    if await _ask_missing_duration(message, state):
        return
    await show_preview(message, state, user)


# ==================== Кнопки меню ====================

@router.message(F.text == "✨ Быстрый ввод")
async def quick_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✨ <b>Быстрый ввод</b>\n\n"
        "Пиши как удобно — ИИ сам поймёт, что это:\n\n"
        "🍽 <i>«Овсянка с бананом и кофе с молоком»</i>\n"
        "🥗 <i>«Обед: борщ, 2 куска хлеба, компот»</i>\n"
        "🍷 <i>«Два бокала вина и сырная тарелка»</i>\n"
        "💧 <i>«Выпила 300 мл воды»</i>\n"
        "🏃 <i>«Пробежал 5 км за 30 минут»</i>\n"
        "🏋️ <i>«Час силовой в зале»</i>\n\n"
        "📸 Фото тарелки · 🎤 голосовое до 1 минуты\n\n"
        "Перед сохранением покажу калории, белки, жиры, углеводы, клетчатку, сахар и жидкость — "
        "можно <b>добавить</b> или <b>исправить</b>."
    )


@router.message(F.text == "💧 Вода")
async def water_button(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_ready(message, state)
    if not user:
        return
    await message.answer(
        f"💧 <b>Сколько воды?</b>\n\nИли напиши любое количество, например <i>«0,7 л воды»</i>.\n\n"
        f"{await diary.liquid_brief_text(user)}",
        reply_markup=get_water_keyboard()
    )


@router.callback_query(F.data.startswith("water:"))
async def water_amount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await ensure_ready(callback.message, state, callback.from_user.id)
    if not user:
        return
    ml = int(callback.data.split(":", 1)[1])
    entry_id = await diary.save_water(user, ml)
    await _safe_edit(
        callback.message,
        f"✅ <b>Записано: {ml} мл воды</b>\n\n{await diary.liquid_brief_text(user)}",
        reply_markup=get_saved_entries_keyboard([('f', entry_id, 'воду')])
    )


# ==================== Голос ====================

@router.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    correction = await state.get_state() in (AIInput.pending_confirmation.state, AIInput.waiting_for_edit.state)
    if not correction:
        await state.clear()
    user = await ensure_ready(message, state)
    if not user:
        return

    voice: Voice = message.voice
    if voice.duration and voice.duration > MAX_VOICE_SECONDS:
        await message.answer(f"🎤 Голосовое длиннее {MAX_VOICE_SECONDS} секунд. Запиши покороче или напиши текстом.")
        return
    limit_message = await check_limit(user, 'voice')
    if limit_message:
        await message.answer(limit_message, reply_markup=get_main_menu())
        return

    await message.answer("🎤 Слушаю...")
    file_path = f"{MEDIA_DIR}/voice/{message.from_user.id}_{datetime.now().timestamp()}.ogg"
    try:
        file = await message.bot.get_file(voice.file_id)
        await message.bot.download_file(file.file_path, file_path)
        text = (await transcribe_voice(file_path)).strip()
        await log_ai(user.telegram_id, 'transcription', 'voice', text, status='added')
    except Exception:
        logger.exception("Ошибка расшифровки голосового")
        await message.answer("❌ Не удалось распознать голосовое. Попробуй ещё раз или напиши текстом.")
        return
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    text = text[:MAX_INPUT_CHARS]
    await message.answer(f"🎤 <i>«{escape(text)}»</i>")
    await run_analysis(message, state, user, text, 'voice', check=False, correction=correction)


# ==================== Фото ====================

@router.message(F.photo)
async def handle_photo_message(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_ready(message, state)
    if not user:
        return
    caption = (message.caption or '').strip()[:MAX_INPUT_CHARS] or None
    limit_message = await check_limit(user, 'photo')
    if limit_message:
        await message.answer(limit_message, reply_markup=get_main_menu())
        return

    await message.answer("📸 Анализирую фото...")
    photo: PhotoSize = message.photo[-1]
    file_path = f"{MEDIA_DIR}/photos/{message.from_user.id}_{datetime.now().timestamp()}.jpg"
    try:
        file = await message.bot.get_file(photo.file_id)
        await message.bot.download_file(file.file_path, file_path)
        await run_analysis(message, state, user, caption, 'photo', image_path=file_path, check=False)
    except Exception:
        logger.exception("Ошибка обработки фото")
        await message.answer("❌ Не удалось обработать фото. Попробуй ещё раз.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ==================== Уточнения и подтверждение ====================

@router.message(AIInput.waiting_for_duration, not_menu_button)
async def process_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip().split()[0])
    except (ValueError, IndexError):
        await message.answer("Напиши длительность числом в минутах, например <i>45</i>.")
        return
    if not 1 <= duration <= 600:
        await message.answer("Длительность — от 1 до 600 минут.")
        return
    data = await state.get_data()
    pending = data['pending']
    pending['result']['workouts'][data.get('duration_index', 0)]['duration_min'] = duration
    await state.update_data(pending=pending)
    user = await diary.get_user(message.from_user.id)
    if await _ask_missing_duration(message, state):
        return
    await show_preview(message, state, user)


@router.message(AIInput.pending_confirmation, not_menu_button)
@router.message(AIInput.waiting_for_edit, not_menu_button)
async def process_correction(message: Message, state: FSMContext):
    """Уточнение к результату текстом: «порция была больше», «там 2 котлеты»"""
    user = await ensure_ready(message, state)
    if not user:
        return
    text = message.text.strip()
    if len(text) > MAX_INPUT_CHARS:
        await message.answer(f"Слишком длинное сообщение — до {MAX_INPUT_CHARS} символов.")
        return
    limit_message = await check_limit(user, 'text')
    if limit_message:
        await message.answer(limit_message, reply_markup=get_main_menu())
        return
    await message.answer("🤖 Учитываю уточнение...")
    await run_analysis(message, state, user, text, 'text', check=False, correction=True)


@router.callback_query(F.data == "ai_edit")
async def edit_pending(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('pending'):
        await callback.answer("Данные устарели, отправь заново")
        return
    await state.set_state(AIInput.waiting_for_edit)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✏️ Напиши, что исправить:\n\n"
        "<i>«Это была большая порция»</i>, <i>«Борщ и 2 котлеты»</i>, <i>«Бег был 40 минут»</i>"
    )
    await callback.answer()


@router.callback_query(F.data == "ai_cancel")
async def cancel_pending(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _safe_edit(callback.message, "❌ Отменено, ничего не записал.")
    await callback.answer()


@router.callback_query(F.data == "ai_confirm")
async def confirm_pending(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pending = data.get('pending')
    if not pending:
        await callback.answer("Данные устарели, отправь заново")
        return
    user = await diary.get_user(callback.from_user.id)
    result = pending['result']
    editing = pending.get('editing')

    if editing:
        kind, entry_id = editing['kind'], editing['id']
        if not await diary.update_entry(kind, entry_id, user, result):
            await callback.answer("Не получилось сохранить исправление", show_alert=True)
            return
        await mark_added(pending.get('interaction_id'), 'calorie_entry' if kind == 'f' else 'workout_entry', entry_id)
        saved = [(kind, entry_id, '')]
        header = "✅ <b>Исправлено!</b>"
    else:
        saved = await diary.save_result(user, result, pending['input_type'], pending.get('text'), result['confidence'])
        first_kind, first_id, _ = saved[0]
        await mark_added(pending.get('interaction_id'),
                         'calorie_entry' if first_kind == 'f' else 'workout_entry', first_id)
        header = "✅ <b>Добавлено!</b>"

    await state.clear()
    names = ", ".join(escape(item['name']) for item in result['items'])
    names += (", " if names and result['workouts'] else "") + ", ".join(
        f"{escape(w['name'])} {w['duration_min']} мин" for w in result['workouts'])
    await _safe_edit(
        callback.message,
        f"{header} {names}\n\n{await diary.day_brief_text(user)}",
        reply_markup=get_saved_entries_keyboard(saved)
    )
    await callback.answer()
    # Тренировка, записанная текстом, могла уже прийти с часов
    from handlers.watch import check_manual_workout
    for kind, entry_id, _ in saved:
        if kind == 'w':
            await check_manual_workout(callback.bot, user, entry_id)


# ==================== Любой текст (последний хэндлер) ====================

@router.message(F.text & ~F.text.startswith('/') & ~F.text.in_(MENU_BUTTONS))
async def handle_text_message(message: Message, state: FSMContext):
    await state.clear()
    user = await ensure_ready(message, state)
    if not user:
        return
    text = message.text.strip()
    if len(text) > MAX_INPUT_CHARS:
        await message.answer(
            f"✂️ Слишком длинное сообщение — до {MAX_INPUT_CHARS} символов. "
            "Опиши еду или тренировку короче."
        )
        return
    limit_message = await check_limit(user, 'text')
    if limit_message:
        await message.answer(limit_message, reply_markup=get_main_menu())
        return
    await message.answer("🤖 Анализирую...")
    await run_analysis(message, state, user, text, 'text', check=False)
