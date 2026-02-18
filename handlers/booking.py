import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import (
    TABLE_PHOTO_PATH, MAX_BOOKING_DAYS,
    WORKING_HOURS_START, WORKING_HOURS_END, SHARED_ORDER_THRESHOLD,
)
from utils import make_kb, cancel_row, back_button, format_date, DAY_NAMES, MONTH_NAMES

from .profile import get_main_kb, is_employee, is_admin

logger = logging.getLogger(__name__)
router = Router()


class BookingStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_people = State()
    waiting_for_table = State()
    waiting_for_time = State()
    waiting_for_preorder = State()
    waiting_for_preorder_amount = State()


#Начало бронирования: выбор даты
@router.callback_query(F.data == "start_booking")
async def booking_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    photo = FSInputFile(TABLE_PHOTO_PATH)
    await callback.message.answer_photo(photo, caption="Схема столов")

    now = datetime.now()
    buttons = []
    for i in range(1, MAX_BOOKING_DAYS + 1):
        day = now + timedelta(days=i)
        day_name = DAY_NAMES[day.weekday()]
        month_name = MONTH_NAMES[day.month - 1]
        date_str = day.strftime("%Y-%m-%d")
        buttons.append([InlineKeyboardButton(
            text=f"{day_name}, {day.day} {month_name}",
            callback_data=f"bdate_{date_str}")])

    buttons.append(cancel_row())
    await callback.message.answer(
        "📅 Выберите дату бронирования:", reply_markup=make_kb(buttons))
    await state.set_state(BookingStates.waiting_for_date)


#Дата выбрана → кол-во людей
@router.callback_query(BookingStates.waiting_for_date, F.data.startswith("bdate_"))
async def booking_date_selected(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_", 1)[1]
    pretty = format_date(date_str)
    await state.update_data(booking_date=date_str, pretty_date=pretty)
    await callback.message.edit_text(f"📅 Дата: {pretty}\n\nНа сколько человек нужен стол?")
    await state.set_state(BookingStates.waiting_for_people)


#Кол-во людей → выбор стола
@router.message(BookingStates.waiting_for_people)
async def booking_people(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число, например: 4")
        return
    count = int(message.text)
    if count < 1:
        await message.answer("⚠️ Минимум 1 человек.")
        return
    await state.update_data(people_count=count)

    tables = db.get_all_tables()
    buttons = []
    for t_id, data in sorted(tables.items(), key=lambda x: x[1]['name']):
        if data['seats'] >= count:
            buttons.append([InlineKeyboardButton(
                text=f"{data['name']} ({data['seats']} мест)",
                callback_data=f"book_tbl_{t_id}")])

    if not buttons:
        await message.answer("😔 Нет подходящих столов для такого количества гостей.",
                             reply_markup=get_main_kb(message.from_user.id))
        await state.clear()
        return

    buttons.append(cancel_row())
    await message.answer("Выберите стол:", reply_markup=make_kb(buttons))
    await state.set_state(BookingStates.waiting_for_table)


#Стол выбран → выбор времени
@router.callback_query(F.data.startswith("book_tbl_"))
async def booking_tbl(callback: CallbackQuery, state: FSMContext):
    t_id = int(callback.data.split("_")[2])
    await state.update_data(table_id=t_id)

    data = await state.get_data()
    booking_date = data.get('booking_date')
    booked_times = db.get_table_bookings(t_id, booking_date)

    buttons = []
    available = 0
    for h in range(WORKING_HOURS_START, WORKING_HOURS_END):
        time_str = f"{h}:00 - {h+1}:00"
        if time_str in booked_times:
            buttons.append([InlineKeyboardButton(text=f"❌ {time_str}", callback_data="noop")])
        else:
            buttons.append([InlineKeyboardButton(text=f"🟢 {time_str}", callback_data=f"time_{h}")])
            available += 1

    if available == 0:
        await callback.message.edit_text(
            "😔 Все слоты на этот день заняты. Попробуйте другую дату.",
            reply_markup=make_kb([back_button("start_booking", "🔙 Выбрать дату")]))
        return

    buttons.append(cancel_row())
    pretty_date = data.get('pretty_date', '')
    await callback.message.edit_text(
        f"📅 Дата: {pretty_date}\nВыберите время:", reply_markup=make_kb(buttons))
    await state.set_state(BookingStates.waiting_for_time)


#Время выбрано → предзаказ?
@router.callback_query(BookingStates.waiting_for_time, F.data.startswith("time_"))
async def booking_time_selection(callback: CallbackQuery, state: FSMContext):
    hour = int(callback.data.split("_")[1])
    time_str = f"{hour}:00 - {hour+1}:00"
    await state.update_data(booking_time=time_str)

    data = await state.get_data()
    pretty = data.get('pretty_date', '')

    kb = make_kb([
        [InlineKeyboardButton(text="Да, предзаказ", callback_data="preorder_yes")],
        [InlineKeyboardButton(text="Нет", callback_data="preorder_no")],
    ])
    await callback.message.edit_text(
        f"📅 Дата: {pretty}\n⏰ Время: {time_str}\n\nПредзаказ?",
        reply_markup=kb)
    await state.set_state(BookingStates.waiting_for_preorder)


#Без предзаказа → подтверждение
@router.callback_query(BookingStates.waiting_for_preorder, F.data == "preorder_no")
async def booking_no_pre(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _create_booking_and_notify(callback, state, data, preorder_sum=0)


#С предзаказом: ввод суммы
@router.callback_query(BookingStates.waiting_for_preorder, F.data == "preorder_yes")
async def booking_yes_pre(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите сумму предзаказа:")
    await state.set_state(BookingStates.waiting_for_preorder_amount)


@router.message(BookingStates.waiting_for_preorder_amount)
async def booking_sum_pre(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите сумму числом, например: 5000")
        return
    val = int(message.text)
    data = await state.get_data()

    # Подменяем callback на message для общей функции
    db.add_booking(message.from_user.id, data['table_id'],
                   data['booking_date'], data['booking_time'],
                   data['people_count'], val)
    booking = db.get_active_booking(message.from_user.id)

    if data['people_count'] > SHARED_ORDER_THRESHOLD:
        order_id, uuid = db.create_order(message.from_user.id, booking_id=booking['id'])
        db.add_order_participant(order_id, message.from_user.id)
        bot_info = await message.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"

        await message.answer(
            f"✅ <b>Бронь с предзаказом ({val}₽) подтверждена!</b>\n"
            f"Создан совместный заказ: {link}",
            parse_mode="HTML",
            reply_markup=get_main_kb(message.from_user.id))
    else:
        await message.answer(
            f"✅ Бронь с предзаказом ({val}₽) подтверждена!",
            reply_markup=get_main_kb(message.from_user.id))

    await state.clear()
    logger.info("Бронь создана: user=%s date=%s", message.from_user.id, data['booking_date'])


async def _create_booking_and_notify(callback: CallbackQuery, state: FSMContext, data: dict, preorder_sum: int):
    """Общая логика создания брони и уведомления."""
    db.add_booking(callback.from_user.id, data['table_id'],
                   data['booking_date'], data['booking_time'],
                   data['people_count'], preorder_sum)
    booking = db.get_active_booking(callback.from_user.id)

    if data['people_count'] > SHARED_ORDER_THRESHOLD:
        order_id, uuid = db.create_order(callback.from_user.id, booking_id=booking['id'])
        db.add_order_participant(order_id, callback.from_user.id)
        bot_info = await callback.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"

        await callback.message.edit_text(
            f"✅ <b>Бронь подтверждена!</b>\n"
            f"Создан <b>Совместный заказ</b> для компании.\n"
            f"Ссылка для гостей: {link}\n\n"
            f"Они смогут добавить блюда в заказ.",
            parse_mode="HTML",
            reply_markup=get_main_kb(callback.from_user.id))
    else:
        await callback.message.edit_text(
            "✅ Бронь подтверждена!",
            reply_markup=get_main_kb(callback.from_user.id))

    await state.clear()
    logger.info("Бронь создана: user=%s date=%s", callback.from_user.id, data['booking_date'])


#Мои брони
@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    booking = db.get_active_booking(callback.from_user.id)
    kb = [back_button()]

    if not booking:
        await callback.message.edit_text("У вас нет активных броней.", reply_markup=make_kb(kb))
        return

    date_info = format_date(booking.get('booking_date', ''))

    text = (
        f"🎫 <b>Ваша бронь:</b>\n\n"
        f"📅 Дата: {date_info}\n"
        f"⏰ Время: {booking['booking_time']}\n"
        f"🪑 Стол: {booking['table_name']}\n"
        f"👥 Гостей: {booking['people_count']}"
    )
    if booking.get('pre_order_sum', 0) > 0:
        text += f"\n💰 Предзаказ: {int(booking['pre_order_sum'])}₽"

    kb.insert(0, [InlineKeyboardButton(text="❌ Отменить бронь", callback_data="cancel_booking")])

    order = db.get_order_by_booking_id(booking['id'])
    if order:
        kb.insert(0, [InlineKeyboardButton(text="🍕 Меню заказа", callback_data=f"open_menu_{order['id']}")])

    await callback.message.edit_text(text, reply_markup=make_kb(kb), parse_mode="HTML")


@router.callback_query(F.data == "cancel_booking")
async def cancel_b(callback: CallbackQuery, state: FSMContext):
    result = db.cancel_booking(callback.from_user.id)
    if result:
        await callback.answer("✅ Бронь отменена")
        logger.info("Бронь отменена: user=%s", callback.from_user.id)
    else:
        await callback.answer("Нет активной брони")
    await state.clear()
    await callback.message.edit_text("Главное меню", reply_markup=get_main_kb(callback.from_user.id))


#Активные брони (сотрудник)
@router.callback_query(F.data == "emp_bookings")
async def emp_bookings(callback: CallbackQuery):
    if not is_employee(callback.from_user.id) and not is_admin(callback.from_user.id):
        return

    bks = db.get_all_bookings_full()
    text = "📋 <b>Активные брони:</b>\n\n"
    found = False

    for b in bks:
        if b['status'] == 'active':
            found = True
            date_fmt = format_date(b.get('booking_date', '') or '')
            text += (
                f"🔹 <b>{date_fmt} {b['booking_time']}</b> — Стол {b['table_name']}\n"
                f"   Гость: {b['user_name']} ({b['people_count']} чел.)\n"
                f"   Тел: {b['phone_number'] or 'не указан'}\n"
            )
            if b.get('pre_order_sum', 0) > 0:
                text += f"   Предзаказ: {int(b['pre_order_sum'])}₽\n"
            text += "\n"

    if not found:
        text += "Нет активных броней."

    await callback.message.edit_text(
        text, reply_markup=make_kb([back_button()]), parse_mode="HTML")
