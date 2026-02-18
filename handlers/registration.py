import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from utils import make_kb

from .profile import get_main_kb
from .menu_order import show_menu

logger = logging.getLogger(__name__)
router = Router()


class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()


# /start
@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext):
    args = command.args
    await state.clear()

    user = db.get_user(message.from_user.id)

    #Не зарегистрирован → регистрация
    if not user:
        await message.answer("Добро пожаловать! Давайте познакомимся.\nКак вас зовут? (ФИО)")
        await state.update_data(next_arg=args)
        await state.set_state(RegistrationStates.waiting_for_name)
        return

    #Присоединение к заказу
    if args and args.startswith("ord_"):
        uuid = args.split("_", 1)[1]
        order = db.get_order_by_uuid(uuid)
        if order and order['status'] == 'open':
            db.add_order_participant(order['id'], message.from_user.id)

            initiator = db.get_user(order['initiator_id'])
            init_name = initiator['full_name'] if initiator else "Инициатора"
            await message.answer(
                f"🍕 Вы присоединились к заказу {init_name}!\n"
                "Всё, что вы выберете, попадет в общую корзину."
            )

            from .menu_order import broadcast_to_order
            await broadcast_to_order(
                message.bot, order['id'],
                f"👋 <b>{user['full_name']}</b> присоединился к заказу!",
                exclude_user_id=message.from_user.id)

            await state.update_data(current_order_id=order['id'])
            await show_menu(message, state, page=1)
            return
        else:
            await message.answer("Ссылка недействительна или заказ закрыт.")

    #Обычный вход
    await message.answer(
        f"👋 Привет, {user['full_name']}!",
        reply_markup=get_main_kb(message.from_user.id))


#Регистрация
@router.message(RegistrationStates.waiting_for_name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = make_kb([[InlineKeyboardButton(text="Пропустить", callback_data="skip_phone")]])
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

    #Присоединение к заказу после регистрации
    args = data.get('next_arg')
    if args and args.startswith("ord_"):
        await message.answer("Регистрация успешна! Переход к заказу…")
        uuid = args.split("_", 1)[1]
        order = db.get_order_by_uuid(uuid)
        if order:
            await state.update_data(current_order_id=order['id'])
            await show_menu(message, state, page=1)
            return

    await message.answer("Регистрация завершена!",
                         reply_markup=get_main_kb(user_obj.id))
    await state.clear()
    logger.info("Новый пользователь: %s (id=%s)", data['name'], user_obj.id)
