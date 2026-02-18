#Всякая дичь
import logging
from datetime import datetime
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# Дни/месяцы
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_NAMES = ["янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек"]


def format_date(date_str: str) -> str:
# форматирование
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{DAY_NAMES[dt.weekday()]}, {dt.day} {MONTH_NAMES[dt.month - 1]}"
    except (ValueError, IndexError):
        return date_str


def back_button(callback_data: str = "start_menu", text: str = "🔙 Назад") -> list:
    return [InlineKeyboardButton(text=text, callback_data=callback_data)]


def cancel_row(callback_data: str = "start_menu") -> list:
    return [InlineKeyboardButton(text="🔙 Отмена", callback_data=callback_data)]


def make_kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)
