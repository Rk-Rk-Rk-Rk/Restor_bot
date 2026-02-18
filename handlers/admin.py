
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from utils import make_kb, back_button, format_date
from .profile import is_admin

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_seats = State()
    waiting_for_menu_name = State()
    waiting_for_menu_price = State()


#Главное меню админки
@router.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    kb = make_kb([
        [InlineKeyboardButton(text="🍔 Управление меню", callback_data="adm_menu_mgmt")],
        [InlineKeyboardButton(text="🪑 Управление столами", callback_data="adm_tables")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users")],
        [InlineKeyboardButton(text="📅 Все брони", callback_data="adm_bookings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        back_button(),
    ])
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb, parse_mode="HTML")


#Меню
@router.callback_query(F.data == "adm_menu_mgmt")
async def adm_menu_mgmt(callback: CallbackQuery):
    items = db.get_all_menu_items()
    kb = []

    if items:
        for item in items:
            kb.append([
                InlineKeyboardButton(
                    text=f"{item['name']} — {int(item['price'])}₽",
                    callback_data="noop"),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"adm_del_menu_{item['id']}"),
            ])

    kb.append([InlineKeyboardButton(text="➕ Добавить позицию", callback_data="adm_add_menu")])
    kb.append(back_button("admin_menu"))

    text = f"🍔 <b>Меню</b> ({len(items)} поз.)\n\nНажмите 🗑 для удаления."
    await callback.message.edit_text(text, reply_markup=make_kb(kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_del_menu_"))
async def adm_del_menu(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[3])
    item = db.get_menu_item(item_id)
    db.delete_menu_item(item_id)
    await callback.answer(f"🗑 {item['name']} удалено" if item else "Удалено")
    logger.info("Удалена позиция меню id=%s", item_id)
    await adm_menu_mgmt(callback)


@router.callback_query(F.data == "adm_add_menu")
async def adm_add_menu_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите название блюда:")
    await state.set_state(AdminStates.waiting_for_menu_name)


@router.message(AdminStates.waiting_for_menu_name)
async def adm_menu_name(message: Message, state: FSMContext):
    await state.update_data(m_name=message.text)
    await message.answer("Цена (числом):")
    await state.set_state(AdminStates.waiting_for_menu_price)


@router.message(AdminStates.waiting_for_menu_price)
async def adm_menu_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число, например: 500")
        return
    data = await state.get_data()
    db.add_menu_item(data['m_name'], int(message.text))
    await message.answer(f"✅ Блюдо «{data['m_name']}» добавлено!")
    await state.clear()
    logger.info("Добавлено блюдо: %s", data['m_name'])


#Столы
@router.callback_query(F.data == "adm_tables")
async def adm_tables(callback: CallbackQuery):
    tables = db.get_all_tables()
    kb = []

    for t_id, data in sorted(tables.items(), key=lambda x: x[1]['name']):
        kb.append([
            InlineKeyboardButton(
                text=f"{data['name']} ({data['seats']} мест)",
                callback_data="noop"),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"adm_del_tbl_{t_id}"),
        ])

    kb.append([InlineKeyboardButton(text="➕ Добавить стол", callback_data="adm_add_tbl")])
    kb.append([InlineKeyboardButton(text="🔄 Сбросить все столы", callback_data="adm_reset")])
    kb.append(back_button("admin_menu"))

    await callback.message.edit_text(
        f"🪑 <b>Столы</b> ({len(tables)} шт.)\n\nНажмите 🗑 для удаления.",
        reply_markup=make_kb(kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_del_tbl_"))
async def adm_del_tbl(callback: CallbackQuery):
    t_id = int(callback.data.split("_")[3])
    db.delete_table(t_id)
    await callback.answer("🗑 Стол удалён")
    logger.info("Удалён стол id=%s", t_id)
    await adm_tables(callback)


@router.callback_query(F.data == "adm_reset")
async def adm_reset(callback: CallbackQuery):
    db.reset_all_tables()
    await callback.answer("🔄 Все столы сброшены, брони отменены")
    logger.info("Сброс всех столов")


@router.callback_query(F.data == "adm_add_tbl")
async def adm_add_t(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите название стола:")
    await state.set_state(AdminStates.waiting_for_name)


@router.message(AdminStates.waiting_for_name)
async def adm_tn(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Количество мест (числом):")
    await state.set_state(AdminStates.waiting_for_seats)


@router.message(AdminStates.waiting_for_seats)
async def adm_ts(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число.")
        return
    data = await state.get_data()
    db.add_table(data['name'], int(message.text))
    await message.answer(f"✅ Стол «{data['name']}» добавлен!")
    await state.clear()
    logger.info("Добавлен стол: %s", data['name'])


#Пользователи

@router.callback_query(F.data == "adm_users")
async def adm_users(callback: CallbackQuery):
    users = db.get_all_users()
    kb = []
    for u in users:
        role_icon = "👮‍♂️" if u['role'] == 'employee' else "👤"
        kb.append([InlineKeyboardButton(
            text=f"{role_icon} {u['full_name']}",
            callback_data=f"adm_user_{u['user_id']}")])
    kb.append(back_button("admin_menu"))

    await callback.message.edit_text(
        f"👥 <b>Пользователи</b> ({len(users)})\n\n"
        "Нажмите для переключения роли (сотрудник ↔ гость).",
        reply_markup=make_kb(kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_user_"))
async def adm_promote(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    user = db.get_user(user_id)
    new_role = 'employee' if user['role'] != 'employee' else 'user'
    db.set_user_role(user_id, new_role)
    role_text = "сотрудник" if new_role == 'employee' else "гость"
    await callback.answer(f"Роль изменена: {role_text}")
    logger.info("Роль user=%s изменена на %s", user_id, new_role)
    await adm_users(callback)


#Брони (админка)

@router.callback_query(F.data == "adm_bookings")
async def adm_bookings(callback: CallbackQuery):
    bks = db.get_all_bookings_full()
    active = [b for b in bks if b['status'] == 'active']

    text = f"📅 <b>Все брони</b> (всего: {len(bks)}, активных: {len(active)})\n\n"

    if not active:
        text += "Нет активных броней."
    else:
        for b in active:
            date_fmt = format_date(b.get('booking_date', '') or '')
            text += (
                f"🔹 <b>{date_fmt} {b['booking_time']}</b>\n"
                f"   Стол: {b['table_name']} | {b['user_name']} ({b['people_count']} чел.)\n"
            )

    kb = []
    for b in active:
        kb.append([InlineKeyboardButton(
            text=f"❌ Удалить #{b['id']}  {b.get('table_name','')}",
            callback_data=f"adm_del_book_{b['id']}")])
    kb.append(back_button("admin_menu"))

    await callback.message.edit_text(text, reply_markup=make_kb(kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_del_book_"))
async def adm_del_booking(callback: CallbackQuery):
    booking_id = int(callback.data.split("_")[3])
    db.delete_booking(booking_id)
    await callback.answer(f"🗑 Бронь #{booking_id} удалена")
    logger.info("Удалена бронь id=%s", booking_id)
    await adm_bookings(callback)


#Статистика
@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    s = db.get_stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {s['users']}\n"
        f"🪑 Столов: {s['tables_count']}\n"
        f"🍔 Позиций меню: {s['menu_count']}\n\n"
        f"📅 Активных броней: {s['active_bookings']}\n"
        f"📅 Всего броней: {s['total_bookings']}\n"
        f"💰 Сумма предзаказов: {int(s['preorder_sum'])}₽\n\n"
        f"📦 Открытых заказов: {s['open_orders']}\n"
        f"✅ Завершённых заказов: {s['closed_orders']}"
    )
    await callback.message.edit_text(
        text, reply_markup=make_kb([back_button("admin_menu")]), parse_mode="HTML")
