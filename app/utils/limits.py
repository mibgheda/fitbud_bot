"""
Дневные лимиты запросов к AI и лог каждого запроса.

Каждый вызов AI пишется в ai_interactions сразу, со статусом:
not_added — проанализировано, но пока не сохранено; added — пользователь добавил запись;
error — запрос не удался. По этому логу считаются лимиты и /balance.
"""
import os
from typing import Optional

from sqlalchemy import select, func

from database.database import async_session, AIInteraction
from utils.daytime import day_bounds

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

DAILY_AI_REQUESTS = 60  # все запросы: текст, голос, фото
DAILY_PHOTOS = 20
MAX_VOICE_SECONDS = 60

# Расшифровка голоса — часть одного запроса, отдельно не считается
COUNTED_TYPES = ('analysis',)


async def check_limit(user, input_type: str) -> Optional[str]:
    """Текст отказа, если дневной лимит исчерпан, иначе None"""
    if user.telegram_id == ADMIN_ID:
        return None
    start, end = day_bounds(user)
    async with async_session() as session:
        base = (
            select(func.count(AIInteraction.id))
            .where(AIInteraction.user_id == user.telegram_id)
            .where(AIInteraction.interaction_type.in_(COUNTED_TYPES))
            .where(AIInteraction.created_at >= start)
            .where(AIInteraction.created_at < end)
        )
        total = (await session.execute(base)).scalar() or 0
        photos = 0
        if input_type == 'photo':
            photos = (await session.execute(base.where(AIInteraction.input_type == 'photo'))).scalar() or 0

    if total >= DAILY_AI_REQUESTS:
        return (
            f"⏳ На сегодня лимит запросов исчерпан ({DAILY_AI_REQUESTS} в день).\n"
            "Завтра снова можно! Посмотреть день — «📋 Мой день»."
        )
    if input_type == 'photo' and photos >= DAILY_PHOTOS:
        return (
            f"⏳ На сегодня лимит фото исчерпан ({DAILY_PHOTOS} в день).\n"
            "Можно написать текстом или надиктовать голосом."
        )
    return None


async def log_ai(user_id: int, interaction_type: str, input_type: str,
                 input_data: Optional[str] = None, response: Optional[dict] = None,
                 usage: Optional[dict] = None, status: str = 'not_added') -> int:
    """Записать запрос к AI, вернуть id записи"""
    usage = usage or {}
    async with async_session() as session:
        log = AIInteraction(
            user_id=user_id,
            interaction_type=interaction_type,
            input_type=input_type,
            input_data=input_data,
            ai_response=response,
            ai_model=usage.get('model'),
            ai_confidence=(response or {}).get('confidence'),
            prompt_tokens=usage.get('prompt_tokens'),
            completion_tokens=usage.get('completion_tokens'),
            total_tokens=usage.get('total_tokens'),
            status=status,
        )
        session.add(log)
        await session.commit()
        return log.id


async def mark_added(interaction_id: Optional[int], entry_type: str, entry_id: int):
    """Пометить запрос как добавленный и связать с записью"""
    if not interaction_id:
        return
    async with async_session() as session:
        log = await session.get(AIInteraction, interaction_id)
        if log:
            log.status = 'added'
            log.created_entry_type = entry_type
            log.created_entry_id = entry_id
            await session.commit()
