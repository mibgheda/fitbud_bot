"""
Разовое обновление профиля при первом же взаимодействии с ботом.

Пользователи, зарегистрированные до версии с часовым поясом, при любом сообщении
или нажатии кнопки (включая /start) сначала отвечают на 3 вопроса: пояс, утро,
активность вне тренировок. Текстовое сообщение, с которым они пришли, запоминается
и разбирается сразу после обновления.
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from handlers.settings import needs_migration, send_migration
from keyboards.reply import MENU_BUTTONS
from utils.diary import get_user
from utils.limits import ADMIN_ID
from utils.openai_helper import MAX_INPUT_CHARS

# Что пропускаем без обновления: удаление аккаунта и админские команды
ALLOWED_COMMANDS = ('/delete_account',)
ADMIN_COMMANDS = ('/broadcast', '/balance', '/users')
ALLOWED_CALLBACKS = ('confirm_delete_account', 'cancel_delete_account')
# Ответы на вопросы обновления
ANSWER_CALLBACKS = ('tz:', 'wake:', 'activity_')
REMINDER = "👆 Сначала ответь на вопрос выше — это займёт полминуты."


def _user_text(event) -> str:
    """Текст пользователя, если это не команда и не кнопка меню"""
    if not isinstance(event, Message):
        return ''
    text = (event.text or '').strip()
    return text if text and not text.startswith('/') and text not in MENU_BUTTONS else ''


class UpdateGate(BaseMiddleware):
    def __init__(self):
        # Кто уже обновлён — чтобы не ходить в базу на каждое сообщение
        self._up_to_date: set = set()

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: Dict[str, Any]) -> Any:
        from_user = data.get('event_from_user')
        state: FSMContext = data.get('state')
        if not from_user or state is None or from_user.id in self._up_to_date:
            return await handler(event, data)

        current = await state.get_state()
        if current and current.startswith('SettingsFlow:'):
            if (await state.get_data()).get('flow') != 'migration':
                return await handler(event, data)
            # Идёт обновление: пропускаем только ответы на вопросы, иначе кнопки меню его оборвут
            if isinstance(event, CallbackQuery) and (event.data or '').startswith(ANSWER_CALLBACKS):
                return await handler(event, data)
            pending = _user_text(event)
            if pending and current == 'SettingsFlow:tz_custom':
                return await handler(event, data)
            if isinstance(event, CallbackQuery):
                await event.answer(REMINDER, show_alert=True)
                return None
            if pending:
                await state.update_data(after_migration_text=pending[:MAX_INPUT_CHARS])
                await event.answer("Запомнил, разберу сразу после обновления. " + REMINDER)
            else:
                await event.answer(REMINDER)
            return None

        text = (event.text or '').strip() if isinstance(event, Message) else ''
        command = text.split()[0].split('@')[0] if text.startswith('/') else ''
        if command in ALLOWED_COMMANDS or (command in ADMIN_COMMANDS and from_user.id == ADMIN_ID):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data in ALLOWED_CALLBACKS:
            return await handler(event, data)

        user = await get_user(from_user.id)
        if not needs_migration(user):
            if user and user.daily_calorie_target:
                self._up_to_date.add(from_user.id)
            return await handler(event, data)

        pending = _user_text(event) or None
        bot = data['bot']
        if isinstance(event, CallbackQuery):
            await event.answer()
            chat_id = event.message.chat.id if event.message else from_user.id
        else:
            chat_id = event.chat.id
        await send_migration(bot, chat_id, state, pending[:MAX_INPUT_CHARS] if pending else None)
        return None
