import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import BOT_TOKEN, ADMIN_IDS

# Инициализация базы при старте
db.init_db()

# --- СОСТОЯНИЯ ---
class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class BookingStates(StatesGroup):
    waiting_for_people = State()
    waiting_for_table = State()
    waiting_for_time = State()
    waiting_for_preorder = State() 
    waiting_for_preorder_amount = State() 

class AdminStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_seats = State()
    # Для добавления меню
    waiting_for_menu_name = State()
    waiting_for_menu_price = State()

# Состояние для просмотра меню
class OrderStates(StatesGroup):
    viewing_menu = State()

router = Router()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_employee(user_id):
    user = db.get_user(user_id)
    return user and user.get('role') == 'employee'


def get_main_kb(user_id):
    kb = [
        [InlineKeyboardButton(text="🍽 Забронировать стол", callback_data="start_booking")],
        [InlineKeyboardButton(text="🎫 Моя бронь", callback_data="my_bookings")],
        [InlineKeyboardButton(text="👤 Кто я?", callback_data="my_profile")]
    ]
    if is_employee(user_id):
        kb.append([InlineKeyboardButton(text="📂 Активные Брони", callback_data="emp_bookings")])
    if is_admin(user_id):
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def broadcast_to_order(bot: Bot, order_id: int, text: str, exclude_user_id=None):
    participants = db.get_order_participants(order_id)
    for p in participants:
         if exclude_user_id and p['user_id'] == exclude_user_id:
             continue
         try:
             await bot.send_message(p['user_id'], text, parse_mode="HTML")
         except:
             pass

#Старт и регистрация
@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext):
    args = command.args
    await state.clear()
    
    # Проверка регистрации   
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Добро пожаловать! Давайте познакомимся.\nКак вас зовут? (ФИО)")
        await state.update_data(next_arg=args)
        await state.set_state(RegistrationStates.waiting_for_name)
        return

    # Обработка присоединения к заказу
    if args and args.startswith("ord_"):
        uuid = args.split("_")[1]
        order = db.get_order_by_uuid(uuid)
        if order and order['status'] == 'open':
            # Присоединяем
            db.add_order_participant(order['id'], message.from_user.id)
            
            initiator = db.get_user(order['initiator_id'])
            init_name = initiator['full_name'] if initiator else "Инициатора"
            await message.answer(f"🍕 Вы присоединились к заказу {init_name}!\nВсё, что вы выберете, попадет в общую корзину.")
            
            # Уведомляем
            await broadcast_to_order(message.bot, order['id'], f"👋 <b>{user['full_name']}</b> присоединился к заказу!", exclude_user_id=message.from_user.id)

            await state.update_data(current_order_id=order['id'])
            
            # Показываем меню
            await show_menu(message, state, page=1)
            return
        else:
            await message.answer("Ссылка недействительна или заказ закрыт.")

    # Обычный старт
    await message.answer(f"👋 Ресторан-бот. Привет, {user['full_name']}!", reply_markup=get_main_kb(message.from_user.id))

@router.message(RegistrationStates.waiting_for_name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="skip_phone")]])
    await message.answer("Телефон? (можно пропустить):", reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.callback_query(RegistrationStates.waiting_for_phone, F.data == "skip_phone")
async def reg_skip_phone(callback: CallbackQuery, state: FSMContext):
    await finish_reg(callback.message, state, callback.from_user, None)

@router.message(RegistrationStates.waiting_for_phone)
async def reg_phone(message: Message, state: FSMContext):
    await finish_reg(message, state, message.from_user, message.text)

async def finish_reg(message: Message, state: FSMContext, user_obj, phone):
    data = await state.get_data()
    db.add_user(user_obj.id, user_obj.username, data['name'], phone)
    
    # Проверяем было ли присоединение к заказу
    args = data.get('next_arg')
    if args and args.startswith("ord_"):
         await message.answer("Регистрация успешна! Переход к заказу...")
         uuid = args.split("_")[1]
         order = db.get_order_by_uuid(uuid)
         if order:
             await state.update_data(current_order_id=order['id'])
             await show_menu(message, state, page=1)
             return

    await message.answer("Регистрация завершена!", reply_markup=get_main_kb(user_obj.id))
    await state.clear()

# совместный заказ, создание
@router.callback_query(F.data == "create_shared_order")
async def create_shared_order(callback: CallbackQuery, state: FSMContext):
    order_id, uuid = db.create_order(callback.from_user.id)
    # Добавляем создателя как участника
    db.add_order_participant(order_id, callback.from_user.id)
    
    bot_info = await callback.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"
    
    await callback.message.edit_text(
        f"✅ <b>Совместный заказ создан!</b>\n\n"
        f"Отправьте участникам эту ссылку:\n{link}\n\n"
        f"Когда они перейдут, они смогут добавлять блюда.\n"
        f"Вы также можете начать выбирать.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Открыть меню", callback_data=f"open_menu_{order_id}")],
            [InlineKeyboardButton(text="🛒 Корзина", callback_data=f"view_cart_{order_id}")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start_menu")]
        ])
    )

# система меню
async def show_menu(ctx: Message, state: FSMContext, page=1, edit=False):
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if not order_id:
        if isinstance(ctx, Message):
             await ctx.answer("Сначала создайте или присоединитесь к заказу.")
        return

    items, has_next = db.get_menu_page(page, per_page=5)
    
    kb = []
    for item in items:
        kb.append([InlineKeyboardButton(
            text=f"{item['name']} - {item['price']}₽", 
            callback_data=f"add_cart_{item['id']}_{page}" # page чтобы вернуться
        )])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅", callback_data=f"menu_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}", callback_data="noop"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡", callback_data=f"menu_page_{page+1}"))
    kb.append(nav_row)
    
    kb.append([InlineKeyboardButton(text="🛒 Корзина", callback_data=f"view_cart_{order_id}")])
    kb.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="start_menu")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    text = "🍕 <b>МЕНЮ</b>\nВыберите блюда:"
    
    if edit and isinstance(ctx, Message):
        await ctx.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await ctx.answer(text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("open_menu_"))
async def open_menu_btn(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    await state.update_data(current_order_id=order_id)
    await show_menu(callback.message, state, page=1, edit=True)

@router.callback_query(F.data.startswith("menu_page_"))
async def menu_nav(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[2])
    await show_menu(callback.message, state, page=page, edit=True)

@router.callback_query(F.data.startswith("add_cart_"))
async def add_cart_item(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    item_id = int(parts[2])
    page = int(parts[3])
    
    data = await state.get_data()
    order_id = data.get('current_order_id')
    
    if order_id:
        db.add_to_cart(order_id, callback.from_user.id, item_id)
        item = db.get_menu_item(item_id)
        
        await callback.answer(f"➕ {item['name']} добавлено!", show_alert=False)
        
        user = db.get_user(callback.from_user.id)
        msg = f"🛒 <b>{user['full_name']}</b> добавил: {item['name']}"
        await broadcast_to_order(callback.message.bot, order_id, msg, exclude_user_id=callback.from_user.id)

# корзина
@router.callback_query(F.data.startswith("view_cart_"))
async def view_cart(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    await state.update_data(current_order_id=order_id)
    
    items = db.get_cart_items(order_id)
    total = sum(i['price'] for i in items)
    
    text = "🛒 <b>Корзина заказа:</b>\n\n"
    if not items:
        text += "Пусто..."
    else:
        for i in items:
            text += f"▪ {i['name']} ({i['price']}₽) — {i['full_name']}\n"
    
    text += f"\n<b>Итого: {total}₽</b>"
    
    kb = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"view_cart_{order_id}")],
        [InlineKeyboardButton(text="📖 В меню", callback_data=f"open_menu_{order_id}")],
        [InlineKeyboardButton(text="💳 Оплатить / Оформить", callback_data=f"checkout_{order_id}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("checkout_"))
async def checkout(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    order = db.get_order_by_id(order_id)
    if order['initiator_id'] != callback.from_user.id:
        await callback.answer("Только инициатор может завершить заказ!", show_alert=True)
        return

    # Пересчет суммы
    total = db.get_order_total(order_id)
    db.close_order(order_id)
    
    msg = f"✅ <b>Заказ оформлен!</b>\n\nСумма к оплате: {total}₽\nОфициант скоро подойдет."
    await callback.message.edit_text(
        msg,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В главное меню", callback_data="start_menu")]])
    )
    
    # Уведомление участников
    await broadcast_to_order(callback.message.bot, order_id, f"🏁 <b>Заказ завершен инициатором!</b>\nИтого: {total}₽", exclude_user_id=callback.from_user.id)

@router.callback_query(F.data == "my_profile")
async def my_profile_handler(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Вы не зарегистрированы?", show_alert=True)
        return
        
    text = (
        f"👤 <b>ВАШ ПРОФИЛЬ</b>\n\n"
        f"Имя: {user['full_name']}\n"
        f"Телефон: {user.get('phone_number') or 'Не указан'}\n"
        f"Статус: {'Постоянный клиент' if user['is_regular'] else 'Гость'}\n"
        f"ID: {user['user_id']}"
    )
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]]), parse_mode="HTML")

# --- БРОНИРОВАНИЕ ---

@router.callback_query(F.data == "start_menu")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню", reply_markup=get_main_kb(callback.from_user.id))

# бронирование столов
@router.callback_query(F.data == "start_booking")
async def booking_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("На сколько человек нужен стол?")
    await state.set_state(BookingStates.waiting_for_people)

@router.message(BookingStates.waiting_for_people)
async def booking_people(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    count = int(message.text)
    await state.update_data(people_count=count)
    tables = db.get_all_tables()
    buttons = []
    for t_id, data in sorted(tables.items(), key=lambda x: x[1]['name']):
        if data['seats'] >= count:
            status = "🟢" if data['status'] == 'free' else "🔴"
            cb = f"book_tbl_{t_id}" if data['status'] == 'free' else "ignore"
            buttons.append([InlineKeyboardButton(text=f"{status} {data['name']}", callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="start_menu")])
    await message.answer("Выберите стол:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(BookingStates.waiting_for_table)

@router.callback_query(F.data.startswith("book_tbl_"))
async def booking_tbl(callback: CallbackQuery, state: FSMContext):
    t_id = int(callback.data.split("_")[2])
    await state.update_data(table_id=t_id)
    await callback.message.edit_text("Введите время:")
    await state.set_state(BookingStates.waiting_for_time)

@router.message(BookingStates.waiting_for_time)
async def booking_time(message: Message, state: FSMContext):
    await state.update_data(booking_time=message.text)
    kb = [[InlineKeyboardButton(text="Да, предзаказ", callback_data="preorder_yes")],
          [InlineKeyboardButton(text="Нет", callback_data="preorder_no")]]
    await message.answer("Предзаказ?", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(BookingStates.waiting_for_preorder)

@router.callback_query(BookingStates.waiting_for_preorder, F.data == "preorder_no")
async def booking_no_pre(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # Создаем бронь
    db.add_booking(callback.from_user.id, data['table_id'], data['booking_time'], data['people_count'])
    
    # Получаем ID только что созданной брони (для связки)
    booking = db.get_active_booking(callback.from_user.id)
    
    # Авто-предложение совместного заказа если > 4 чел
    if data['people_count'] > 4:
        # Создаем заказ автоматически связанный с бронью
        order_id, uuid = db.create_order(callback.from_user.id, booking_id=booking['id'])
        db.add_order_participant(order_id, callback.from_user.id)
        
        bot_info = await callback.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"
        
        await callback.message.edit_text(
            f"✅ <b>Бронь подтверждена!</b>\n"
            f"Так как вас много, я создал <b>Совместный заказ</b>.\n"
            f"Ссылка для гостей: {link}\n\n"
            f"Они смогут сами добавить блюда в заказ.",
            parse_mode="HTML",
            reply_markup=get_main_kb(callback.from_user.id)
        )
    else:
        await callback.message.edit_text("Бронь подтверждена!", reply_markup=get_main_kb(callback.from_user.id))
    
    await state.clear()

@router.callback_query(BookingStates.waiting_for_preorder, F.data == "preorder_yes")
async def booking_yes_pre(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите сумму предзаказа:") 
    await state.set_state(BookingStates.waiting_for_preorder_amount)

@router.message(BookingStates.waiting_for_preorder_amount)
async def booking_sum_pre(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    val = int(message.text)
    data = await state.get_data()
    db.add_booking(message.from_user.id, data['table_id'], data['booking_time'], data['people_count'], val)
    
    booking = db.get_active_booking(message.from_user.id)
    # То же самое для предзаказа с суммой
    if data['people_count'] > 4:
         order_id, uuid = db.create_order(message.from_user.id, booking_id=booking['id'])
         db.add_order_participant(order_id, message.from_user.id)
         bot_info = await message.bot.get_me()
         link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"
         
         await message.answer(
            f"✅ <b>Бронь с предзаказом ({val}р) ОК!</b>\n"
            f"Создан совместный заказ для компании: {link}",
            parse_mode="HTML",
            reply_markup=get_main_kb(message.from_user.id)
         )
    else:
        await message.answer("Бронь с предзаказом ОК!", reply_markup=get_main_kb(message.from_user.id))
    
    await state.clear()

@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    booking = db.get_active_booking(callback.from_user.id)
    text = "Нет броней"
    kb = [[InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]]
    if booking:
        text = f"Бронь: {booking['table_name']} в {booking['booking_time']}"
        kb.insert(0, [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking")])
        
        # Проверка на связанный заказ
        order = db.get_order_by_booking_id(booking['id'])
        if order:
            kb.insert(0, [InlineKeyboardButton(text="🍕 Меню заказа", callback_data=f"open_menu_{order['id']}")])
            
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "cancel_booking")
async def cancel_b(callback: CallbackQuery, state: FSMContext):
    db.cancel_booking(callback.from_user.id)
    await callback.answer("Отменено")
    await back_to_main(callback, state)

@router.callback_query(F.data == "emp_bookings")
async def emp_bookings(c: CallbackQuery):
    if not is_employee(c.from_user.id) and not is_admin(c.from_user.id):
        return
    bks = db.get_all_bookings_full()
    text = f"📋 <b>Активные брони:</b>\n\n"
    found = False
    for b in bks:
        if b['status'] == 'active':
            found = True
            text += f"🔹 <b>{b['booking_time']}</b> - Стол {b['table_name']}\n"
            text += f"   Гость: {b['user_name']} ({b['people_count']} чел.)\n"
            text += f"   Тел: {b['phone_number']}\n\n"
    
    if not found:
        text += "Нет активных броней."
            
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]]), parse_mode="HTML")

# админ панель
@router.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = [
        [InlineKeyboardButton(text="🍔 Управление меню", callback_data="adm_menu_mgmt")],
        [InlineKeyboardButton(text="👥 Юзеры", callback_data="adm_users")],
        [InlineKeyboardButton(text="📅 Брони", callback_data="adm_bookings")],
        [InlineKeyboardButton(text="🪑 Столы", callback_data="adm_tables")],
        [InlineKeyboardButton(text="🔙 Выход", callback_data="start_menu")]
    ]
    await callback.message.edit_text("Админка:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "adm_menu_mgmt")
async def adm_menu_mgmt(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="➕ Добавить позицию", callback_data="adm_add_menu")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")]
    ]
    await callback.message.edit_text("Меню админ:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "adm_add_menu")
async def adm_add_menu_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Название блюда:")
    await state.set_state(AdminStates.waiting_for_menu_name)

@router.message(AdminStates.waiting_for_menu_name)
async def adm_menu_name(message: Message, state: FSMContext):
    await state.update_data(m_name=message.text)
    await message.answer("Цена (числом):")
    await state.set_state(AdminStates.waiting_for_menu_price)

@router.message(AdminStates.waiting_for_menu_price)
async def adm_menu_price(message: Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    db.add_menu_item(data['m_name'], int(message.text))
    await message.answer("Блюдо добавлено!", reply_markup=get_main_kb(message.from_user.id))
    await state.clear()

# Admin: Promote User
@router.callback_query(F.data == "adm_users")
async def adm_users(c: CallbackQuery):
    users = db.get_all_users()
    kb = []
    for u in users:
        role_icon = "👮‍♂️" if u['role'] == 'employee' else "👤"
        kb.append([InlineKeyboardButton(text=f"{role_icon} {u['full_name']}", callback_data=f"adm_user_{u['user_id']}")])
    kb.append([InlineKeyboardButton(text="🔙", callback_data="admin_menu")])
    
    await c.message.edit_text(f"Юзеров: {len(users)}\nНажмите, чтобы сделать сотрудником.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("adm_user_"))
async def adm_promote(c: CallbackQuery):
    user_id = int(c.data.split("_")[2])
    user = db.get_user(user_id)
    new_role = 'employee' if user['role'] != 'employee' else 'user'
    db.set_user_role(user_id, new_role)
    await c.answer(f"Роль изменена на {new_role}")
    await adm_users(c)

@router.callback_query(F.data == "adm_bookings")
async def adm_bookings(c: CallbackQuery):
    bks = db.get_all_bookings_full()
    await c.message.edit_text(f"Броней: {len(bks)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_menu")]]))

@router.callback_query(F.data == "adm_tables")
async def adm_tables(c: CallbackQuery):
    await c.message.edit_text("Управление столами...", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить", callback_data="adm_add")],
        [InlineKeyboardButton(text="Сброс", callback_data="adm_reset")],
        [InlineKeyboardButton(text="🔙", callback_data="admin_menu")]
    ]))

@router.callback_query(F.data == "adm_reset")
async def adm_reset(c: CallbackQuery):
    db.reset_all_tables()
    await c.answer("Сброшено")

@router.callback_query(F.data == "adm_add")
async def adm_add_t(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Название стола:")
    await state.set_state(AdminStates.waiting_for_name)

@router.message(AdminStates.waiting_for_name)
async def adm_tn(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("Мест:")
    await state.set_state(AdminStates.waiting_for_seats)

@router.message(AdminStates.waiting_for_seats)
async def adm_ts(m: Message, state: FSMContext):
    data = await state.get_data()
    db.add_table(data['name'], int(m.text))
    await m.answer("Стол добавлен", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
