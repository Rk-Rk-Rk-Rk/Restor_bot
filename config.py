import os

# Токен бота
BOT_TOKEN = "TOKEN"

# Имя файла базы данных
DB_NAME = "restaurant.db"

# ID админов
ADMIN_IDS = [
    1577353727,
]

# Название ресторана
RESTAURANT_NAME = "RE-STOR"

# Путь к изображению схемы столов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TABLE_PHOTO_PATH = os.path.join(BASE_DIR, "OKOSAURIONA.png")

# Позиций меню на страницу
ITEMS_PER_PAGE = 5

# Рабочие часы ресторана
WORKING_HOURS_START = 8
WORKING_HOURS_END = 22

# Максимум дней вперёд для бронирования
MAX_BOOKING_DAYS = 7

# Порог людей создания совместного заказа
SHARED_ORDER_THRESHOLD = 4
