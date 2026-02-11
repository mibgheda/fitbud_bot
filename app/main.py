import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import os

from database.database import init_db
from handlers import start, calories, fitness, profile, stats, ai_hub

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
    
    # Подключаем роутеры из handlers
    # Порядок важен: конкретные хэндлеры (кнопки меню, FSM-состояния) — первыми,
    # ai_hub (catch-all для текста) — последним, чтобы не перехватывать кнопки меню
    dp.include_router(start.router)
    dp.include_router(calories.router)
    dp.include_router(fitness.router)
    dp.include_router(profile.router)
    dp.include_router(stats.router)
    dp.include_router(ai_hub.router)
    
    # Инициализация базы данных
    await init_db()
    
    logger.info("Бот запущен v5 (quick input, new_day, delete_account)")
    
    try:
        # Запуск бота
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
