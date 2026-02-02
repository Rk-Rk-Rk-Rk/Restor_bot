import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import BOT_TOKEN

# импорт базы данных
import database as db

db.init_db()

class AdminStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_seats = State()
    waiting_for_neighbors = State() 

router = Router()

# КЛАВИАТУРЫ
def get_main_kb(is_admin=True):     
    kb = [
        [InlineKeyboardButton(text="👤 Забронировать", callback_data="mode_single")],
        [InlineKeyboardButton(text="👥 Большая компания", callback_data="mode_party")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="🛠 Админка", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_tables_kb(tables, callback_prefix, filter_status=None):
    buttons = []
    for t_id, data in tables.items():
        if filter_status and data['status'] != filter_status:
            continue
            
        icon = "🟢" if data['status'] == 'free' else "🔴"
        text = f"{icon} {data['name']} ({data['seats']})"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"{callback_prefix}_{t_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ЛОГИКА КЛИЕНТА
@router.message(Command("start"))
async def start(message: Message):
    await message.answer("Здравствуйте! Вас приветствует ресторан 'RESTOR'.", reply_markup=get_main_kb())

@router.callback_query(F.data == "start_menu")
async def back(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню", reply_markup=get_main_kb())

# Бронь одиночного
@router.callback_query(F.data == "mode_single")
async def show_single(callback: CallbackQuery):
    tables = db.get_all_tables()
    await callback.message.edit_text("Выберите стол:", reply_markup=get_tables_kb(tables, "book"))

@router.callback_query(F.data.startswith("book_"))
async def process_book(callback: CallbackQuery):
    t_id = int(callback.data.split("_")[1])
    tables = db.get_all_tables()
    
    if tables[t_id]['status'] != 'free':
        await callback.answer("Уже занято!", show_alert=True)
        return

    db.update_status(t_id, 'busy')
    await callback.message.edit_text(f"✅ Стол {tables[t_id]['name']} забронирован!", reply_markup=get_main_kb())

# Умное объединение
@router.callback_query(F.data == "mode_party")
async def show_party(callback: CallbackQuery):
    tables = db.get_all_tables()
    buttons = []
    checked_pairs = set()
    found = False

    for t_id, data in tables.items():
        if data['status'] == 'free':
            for n_id in data['neighbors']:
                if n_id in tables and tables[n_id]['status'] == 'free':
                    pair = tuple(sorted((t_id, n_id)))
                    if pair not in checked_pairs:
                        checked_pairs.add(pair)
                        found = True
                        text = f"✨ {data['name']} + {tables[n_id]['name']}"
                        buttons.append([InlineKeyboardButton(text=text, callback_data=f"merge_{pair[0]}_{pair[1]}")])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")])
    msg = "Варианты для компании:" if found else "Нет свободных пар столов."
    await callback.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("merge_"))
async def process_merge(callback: CallbackQuery):
    _, id1, id2 = callback.data.split("_")
    db.update_status(int(id1), 'busy')
    db.update_status(int(id2), 'busy')
    await callback.message.edit_text("Двойная бронь подтверждена!", reply_markup=get_main_kb())

# АДМИНКА
@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="➕ Добавить стол", callback_data="adm_add")],
        [InlineKeyboardButton(text="🗑 Удалить стол", callback_data="adm_del")],
        [InlineKeyboardButton(text="🔓 Сбросить статусы", callback_data="adm_reset")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]
    ]
    await callback.message.edit_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Сценарий добавления стола с соседями
@router.callback_query(F.data == "adm_add")
async def add_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите название стола:")
    await state.set_state(AdminStates.waiting_for_name)

@router.message(AdminStates.waiting_for_name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Количество мест (число):")
    await state.set_state(AdminStates.waiting_for_seats)

@router.message(AdminStates.waiting_for_seats)
async def add_seats(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число!")
        return
    await state.update_data(seats=int(message.text), neighbors=[])
    
    # Переходим к выбору соседей
    tables = db.get_all_tables()
    if not tables:
        await finish_add_table(message, state)
    else:
        await show_neighbor_selection(message, tables, [])
        await state.set_state(AdminStates.waiting_for_neighbors)

async def show_neighbor_selection(message, tables, selected_ids):
    buttons = []
    for t_id, data in tables.items():
        mark = "✅" if t_id in selected_ids else "⬜"
        buttons.append([InlineKeyboardButton(
            text=f"{mark} {data['name']}", 
            callback_data=f"toggle_neighbor_{t_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="💾 Готово", callback_data="save_neighbors")])
    
    if isinstance(message, Message):
        await message.answer("Выберите соседние столы (для объединения):", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("toggle_neighbor_"))
async def toggle_neighbor(callback: CallbackQuery, state: FSMContext):
    t_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    current_list = data.get('neighbors', [])
    
    if t_id in current_list:
        current_list.remove(t_id)
    else:
        current_list.append(t_id)
    
    await state.update_data(neighbors=current_list)
    tables = db.get_all_tables()
    await show_neighbor_selection(callback.message, tables, current_list)

@router.callback_query(F.data == "save_neighbors")
async def save_neighbors_finish(callback: CallbackQuery, state: FSMContext):
    await finish_add_table(callback.message, state, is_edit=True)

async def finish_add_table(message: Message, state: FSMContext, is_edit=False):
    data = await state.get_data()
    db.add_table(data['name'], data['seats'], data['neighbors'])
    text = f"✅ Стол '{data['name']}' создан! Соседей: {len(data['neighbors'])}"
    if is_edit:
        await message.edit_text(text, reply_markup=get_main_kb())
    else:
        await message.answer(text, reply_markup=get_main_kb())
    await state.clear()

# просто вызовы БД
@router.callback_query(F.data == "adm_reset")
async def reset_all(callback: CallbackQuery):
    tables = db.get_all_tables()
    for t_id in tables:
        db.update_status(t_id, 'free')
    await callback.answer("База сброшена!", show_alert=True)

@router.callback_query(F.data == "adm_del")
async def del_menu(callback: CallbackQuery):
    tables = db.get_all_tables()
    await callback.message.edit_text("Удалить:", reply_markup=get_tables_kb(tables, "del_conf"))

@router.callback_query(F.data.startswith("del_conf_"))
async def del_confirm(callback: CallbackQuery):
    t_id = int(callback.data.split("_")[2])
    db.delete_table(t_id)
    await callback.message.edit_text("Удалено!", reply_markup=get_main_kb())

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
