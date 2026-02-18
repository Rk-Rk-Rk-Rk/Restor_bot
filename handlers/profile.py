import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

import database as db
from config import ADMIN_IDS, RESTAURANT_NAME
from utils import make_kb, back_button, format_date

logger = logging.getLogger(__name__)
router = Router()


# Вспомогательные 
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_employee(user_id: int) -> bool:
    user = db.get_user(user_id)
    return user is not None and user.get('role') == 'employee'


def get_main_kb(user_id: int):
    kb = [
        [InlineKeyboardButton(text="🍽 Забронировать стол", callback_data="start_booking")],
        [InlineKeyboardButton(text="🎫 Моя бронь", callback_data="my_bookings")],
        [InlineKeyboardButton(text="👤 Кто я?", callback_data="my_profile")],
    ]
    if is_employee(user_id):
        kb.append([InlineKeyboardButton(text="📂 Активные Брони", callback_data="emp_bookings")])
    if is_admin(user_id):
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_menu")])
    return make_kb(kb)


#Главное меню
@router.callback_query(F.data == "start_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню", reply_markup=get_main_kb(callback.from_user.id))


# Профиль 
@router.callback_query(F.data == "my_profile")
async def my_profile_handler(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Вы не зарегистрированы!", show_alert=True)
        return

    # История броней
    history = db.get_user_bookings_history(callback.from_user.id, limit=5)
    history_text = ""
    if history:
        history_text = "\n\n📖 <b>Последние брони:</b>\n"
        for h in history:
            status_icon = "✅" if h['status'] == 'active' else "❌"
            date_pretty = format_date(h.get('booking_date', ''))
            history_text += f"{status_icon} {date_pretty} {h['booking_time']} — {h['table_name']}\n"

    text = (
        f"👤 <b>ВАШ ПРОФИЛЬ</b>\n\n"
        f"Имя: {user['full_name']}\n"
        f"Телефон: {user.get('phone_number') or 'Не указан'}\n"
        f"Статус: {'⭐ Постоянный клиент' if user['is_regular'] else '👤 Гость'}\n"
        f"ID: <code>{user['user_id']}</code>"
        f"{history_text}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=make_kb([back_button()]),
        parse_mode="HTML")


# /help
@router.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        f"ℹ️ <b>{RESTAURANT_NAME} — Справка</b>\n\n"
        "🍽 <b>Забронировать стол</b> — выберите дату, количество гостей, стол и время\n"
        "🎫 <b>Моя бронь</b> — просмотр и отмена текущей брони\n"
        "👤 <b>Кто я?</b> — ваш профиль и история\n"
        "🍕 <b>Совместный заказ</b> — создайте общий заказ и поделитесь ссылкой\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/help — эта справка"
    )
    await message.answer(text, parse_mode="HTML")
