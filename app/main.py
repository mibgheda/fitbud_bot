import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy import select
import os

from database.database import init_db, async_session, ScheduledPost, User
from handlers import start, calories, fitness, profile, stats, plans, ai_hub

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def scheduled_posts_worker(bot: Bot):
    """Фоновая задача: каждые 60 секунд проверяет и отправляет запланированные посты"""
    while True:
        try:
            now = datetime.utcnow()
            async with async_session() as session:
                result = await session.execute(
                    select(ScheduledPost)
                    .where(ScheduledPost.is_sent == False, ScheduledPost.scheduled_at <= now)  # noqa: E712
                    .order_by(ScheduledPost.scheduled_at)
                )
                posts = result.scalars().all()

                for post in posts:
                    # Получаем всех пользователей
                    users_result = await session.execute(select(User.telegram_id))
                    user_ids = [row[0] for row in users_result.all()]

                    sent = 0
                    failed = 0
                    for i, user_id in enumerate(user_ids):
                        try:
                            await bot.send_message(user_id, post.text)
                            sent += 1
                        except Exception as e:
                            failed += 1
                            logger.warning(f"Scheduled post #{post.id} failed for {user_id}: {e}")
                        if (i + 1) % 25 == 0:
                            await asyncio.sleep(1)

                    post.is_sent = True
                    post.sent_at = datetime.utcnow()
                    logger.info(f"Scheduled post #{post.id} sent: {sent} ok, {failed} failed")

                if posts:
                    await session.commit()
        except Exception as e:
            logger.error(f"scheduled_posts_worker error: {e}")

        await asyncio.sleep(60)


async def main():
    """Главная функция запуска бота"""
    # Инициализация бота
    bot = Bot(
        token=os.getenv('BOT_TOKEN'),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Подключаем роутеры из handlers
    # Порядок важен: конкретные хэндлеры (кнопки меню, FSM-состояния) — первыми,
    # ai_hub (catch-all для текста) — последним, чтобы не перехватывать кнопки меню
    dp.include_router(start.router)
    dp.include_router(calories.router)
    dp.include_router(fitness.router)
    dp.include_router(profile.router)
    dp.include_router(stats.router)
    dp.include_router(plans.router)
    dp.include_router(ai_hub.router)
    
    # Инициализация базы данных
    await init_db()
    
    logger.info("Бот запущен v7 (meal plan, workout plan)")
    
    try:
        # Запуск фонового воркера запланированных постов
        worker_task = asyncio.create_task(scheduled_posts_worker(bot))
        # Запуск бота
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        worker_task.cancel()
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
