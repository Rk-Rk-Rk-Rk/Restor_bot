import asyncio
import logging

from aiogram import Bot, Dispatcher

import database as db
from config import BOT_TOKEN
from handlers import get_all_routers

#Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    #Инициализация базы
    db.init_db()
    logger.info("БД инициализирована")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    #Подключение всех роутеров
    for r in get_all_routers():
        dp.include_router(r)

    logger.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
