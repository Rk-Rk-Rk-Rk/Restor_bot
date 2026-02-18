import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import ITEMS_PER_PAGE
from utils import make_kb, back_button

from .profile import get_main_kb

logger = logging.getLogger(__name__)
router = Router()


class OrderStates(StatesGroup):
    viewing_menu = State()


#Отправить сообщение всем участникам заказа
async def broadcast_to_order(bot: Bot, order_id: int, text: str, exclude_user_id=None):
    participants = db.get_order_participants(order_id)
    for p in participants:
        if exclude_user_id and p['user_id'] == exclude_user_id:
            continue
        try:
            await bot.send_message(p['user_id'], text, parse_mode="HTML")
        except Exception as e:
            logger.warning("Не удалось отправить уведомление user=%s: %s", p['user_id'], e)


#Создание совместного заказа
@router.callback_query(F.data == "create_shared_order")
async def create_shared_order(callback: CallbackQuery, state: FSMContext):
    order_id, uuid = db.create_order(callback.from_user.id)
    db.add_order_participant(order_id, callback.from_user.id)

    bot_info = await callback.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ord_{uuid}"

    await callback.message.edit_text(
        f"✅ <b>Совместный заказ создан!</b>\n\n"
        f"Отправьте участникам эту ссылку:\n{link}\n\n"
        f"Когда они перейдут, они смогут добавлять блюда.\n"
        f"Вы также можете начать выбирать.",
        parse_mode="HTML",
        reply_markup=make_kb([
            [InlineKeyboardButton(text="📖 Открыть меню", callback_data=f"open_menu_{order_id}")],
            [InlineKeyboardButton(text="🛒 Корзина", callback_data=f"view_cart_{order_id}")],
            back_button(),
        ]))


#Отображение меню
async def show_menu(ctx: Message, state: FSMContext, page=1, edit=False):
    data = await state.get_data()
    order_id = data.get('current_order_id')

    if not order_id:
        if isinstance(ctx, Message):
            await ctx.answer("Сначала создайте или присоединитесь к заказу.")
        return

    items, has_next = db.get_menu_page(page, per_page=ITEMS_PER_PAGE)

    kb = []
    for item in items:
        kb.append([InlineKeyboardButton(
            text=f"{item['name']} — {int(item['price'])}₽",
            callback_data=f"add_cart_{item['id']}_{page}")])

    # Навигация
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅", callback_data=f"menu_page_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}", callback_data="noop"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡", callback_data=f"menu_page_{page+1}"))
    kb.append(nav)

    kb.append([InlineKeyboardButton(text="🛒 Корзина", callback_data=f"view_cart_{order_id}")])
    kb.append(back_button())

    text = "🍕 <b>МЕНЮ</b>\nВыберите блюда:"
    markup = make_kb(kb)

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


#Добавление в корзину
@router.callback_query(F.data.startswith("add_cart_"))
async def add_cart_item(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    item_id = int(parts[2])
    page = int(parts[3])

    data = await state.get_data()
    order_id = data.get('current_order_id')

    if not order_id:
        await callback.answer("Нет активного заказа!", show_alert=True)
        return

    db.add_to_cart(order_id, callback.from_user.id, item_id)
    item = db.get_menu_item(item_id)
    await callback.answer(f"➕ {item['name']} добавлено!", show_alert=False)

    user = db.get_user(callback.from_user.id)
    await broadcast_to_order(
        callback.message.bot, order_id,
        f"🛒 <b>{user['full_name']}</b> добавил: {item['name']}",
        exclude_user_id=callback.from_user.id)


#Корзина
@router.callback_query(F.data.startswith("view_cart_"))
async def view_cart(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    await state.update_data(current_order_id=order_id)

    items = db.get_cart_items(order_id)
    total = sum(i['price'] for i in items)

    text = "🛒 <b>Корзина заказа:</b>\n\n"
    if not items:
        text += "Пусто…"
    else:
        for idx, i in enumerate(items, 1):
            text += f"{idx}. {i['name']} ({int(i['price'])}₽) — {i['full_name']}\n"

    text += f"\n<b>Итого: {int(total)}₽</b>"

    kb = []

    # Кнопки удаления позиций
    if items:
        for i in items:
            kb.append([InlineKeyboardButton(
                text=f"🗑 {i['name']}",
                callback_data=f"rmcart_{i['cart_id']}_{order_id}")])

    kb.extend([
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"view_cart_{order_id}")],
        [InlineKeyboardButton(text="📖 В меню", callback_data=f"open_menu_{order_id}")],
        [InlineKeyboardButton(text="💳 Оплатить / Оформить", callback_data=f"checkout_{order_id}")],
    ])

    await callback.message.edit_text(text, reply_markup=make_kb(kb), parse_mode="HTML")


#Удаление из корзины
@router.callback_query(F.data.startswith("rmcart_"))
async def remove_cart(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cart_item_id = int(parts[1])
    order_id = int(parts[2])

    db.remove_cart_item(cart_item_id)
    await callback.answer("🗑 Удалено из корзины")
    logger.info("Удалена позиция корзины id=%s", cart_item_id)

    # Перерисовать корзину
    callback.data = f"view_cart_{order_id}"
    await view_cart(callback, state)


#Проверки
@router.callback_query(F.data.startswith("checkout_"))
async def checkout(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    order = db.get_order_by_id(order_id)

    if not order:
        await callback.answer("Заказ не найден!", show_alert=True)
        return

    if order['initiator_id'] != callback.from_user.id:
        await callback.answer("Только инициатор может завершить заказ!", show_alert=True)
        return

    total = db.get_order_total(order_id)

    if total == 0:
        await callback.answer("Корзина пуста! Добавьте блюда.", show_alert=True)
        return

    db.close_order(order_id)

    msg = f"✅ <b>Заказ оформлен!</b>\n\nСумма к оплате: {int(total)}₽\nОфициант скоро подойдет."
    await callback.message.edit_text(
        msg, parse_mode="HTML",
        reply_markup=make_kb([back_button()]))

    await broadcast_to_order(
        callback.message.bot, order_id,
        f"🏁 <b>Заказ завершен!</b>\nИтого: {int(total)}₽",
        exclude_user_id=callback.from_user.id)

    logger.info("Заказ #%s оформлен, сумма=%s", order_id, total)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
