import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import os

from database.database import init_db
from middlewares.update_gate import UpdateGate
from handlers import start, settings, calories, fitness, profile, stats, plans, day, watch, ai_hub
from api import health_api

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота"""
    # Инициализация бота
    bot = Bot(
        token=os.getenv('BOT_TOKEN'),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Инициализация диспетчера
    dp = Dispatcher()
    
    # Пользователи старой версии при любом взаимодействии сначала проходят разовое обновление профиля
    update_gate = UpdateGate()
    dp.message.outer_middleware(update_gate)
    dp.callback_query.outer_middleware(update_gate)

    # Подключаем роутеры из handlers
    # Порядок важен: конкретные хэндлеры (кнопки меню, FSM-состояния) — первыми,
    # ai_hub (catch-all для текста) — последним, чтобы не перехватывать кнопки меню
    dp.include_router(start.router)
    dp.include_router(settings.router)
    dp.include_router(calories.router)
    dp.include_router(fitness.router)
    dp.include_router(profile.router)
    dp.include_router(stats.router)
    dp.include_router(plans.router)
    dp.include_router(day.router)
    dp.include_router(watch.router)  # до ai_hub: быстрая правка записи перехватывает текст раньше AI
    dp.include_router(ai_hub.router)
    
    # Инициализация базы данных
    await init_db()
    
    logger.info("Бот запущен v9 (+ часы Apple Watch через команду iPhone)")
    
    # API для часов (команда iPhone) — если задан порт
    api_runner = None
    if os.getenv('HEALTH_API_PORT'):
        api_runner = await health_api.start(bot, int(os.getenv('HEALTH_API_PORT')))

    try:
        # Запуск бота
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if api_runner:
            await api_runner.cleanup()
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
