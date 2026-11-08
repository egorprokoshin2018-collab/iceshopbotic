import asyncio
import json

import asyncio
import json
import re

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo,
)

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "9227073224:AAHckxwD2-CFWho-_TELuysoEDXXg7cy9h4"             # свежий токен из @BotFather
ADMIN_ID = 8915050007                       # твой Telegram ID
CHANNEL = "https://t.me/iceshop29"          # ссылка на канал
WEBAPP_URL = "https://egorprokoshin2018-collab.github.io/iceshop/"
MANAGER_URL = "https://t.me/manager_ice_shop"

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

orders = {}          # id заказа -> данные
order_counter = [0]  # счётчик заказов


class States(StatesGroup):
    user_chat = State()    # клиент пишет в поддержку/менеджеру
    admin_reply = State()  # админ отвечает клиенту


# ===== КЛАВИАТУРЫ =====

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍 Открыть магазин",
                            web_app=WebAppInfo(url=WEBAPP_URL))],
            [KeyboardButton(text="💬 Связаться с поддержкой")],
        ],
        resize_keyboard=True,
    )


def dialog_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔒 Закрыть диалог")]],
        resize_keyboard=True,
    )


def admin_msg_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Ответить", callback_data=f"reply:{user_id}"),
         InlineKeyboardButton(text="🔒 Закрыть диалог", callback_data=f"close_admin:{user_id}")],
    ])


def channel_username() -> str:
    return "@" + CHANNEL.rstrip("/").split("/t.me/")[-1]


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_username(), user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return True


async def remove_notice(oid):
    """Убирает кнопку «Написать менеджеру» у клиента."""
    o = orders.get(oid)
    if o and o.get("notice_id"):
        try:
            await bot.edit_message_reply_markup(chat_id=o["user_id"],
                                                message_id=o["notice_id"],
                                                reply_markup=None)
        except Exception:
            pass
        o["notice_id"] = None


# ===== СТАРТ И ПОДПИСКА =====

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    if await is_subscribed(message.from_user.id):
        await message.answer(
            "👋 Здравствуйте! Добро пожаловать в Ice Shop.\n\n"
            "Здесь вы можете посмотреть товары в наличии и оформить заказ.",
            reply_markup=main_menu(),
        )
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="i_subscribed")],
        ])
        await message.answer(
            "👋 Здравствуйте! Добро пожаловать в Ice Shop.\n\n"
            "Перед тем как оформить заказ или посмотреть наличие, "
            "нужно подписаться на наш Telegram-канал.",
            reply_markup=kb,
        )


@dp.callback_query(F.data == "i_subscribed")
async def i_subscribed(cb: CallbackQuery, state: FSMContext):
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text("✅ Спасибо за подписку!")
        await bot.send_message(cb.from_user.id, "Выберите действие:",
                               reply_markup=main_menu())
        await cb.answer()
    else:
        await cb.answer("Вы ещё не подписаны на канал!", show_alert=True)


# ===== МАГАЗИН: ПРИЁМ ЗАКАЗА =====

@dp.message(F.web_app_data)
async def new_order(message: Message):
    print("ПОЛУЧЕНЫ ДАННЫЕ:", message.web_app_data.data)
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        print("ОШИБКА РАЗБОРА:", e)
        return

    def field(*names):
        for n in names:
            v = data.get(n)
            if v:
                return v
        return "—"

    items = data.get("items")
    items_str = "\n".join("• " + str(i) for i in items) if isinstance(items, list) else str(items or "—")

    order_counter[0] += 1
    oid = order_counter[0]
    orders[oid] = {
        "user_id": message.from_user.id,
        "notice_id": None,
        "text": (
            f"🛒 <b>Новый заказ #{oid}</b>\n\n"
            f"📦 Товары:\n{items_str}\n"
            f"💰 Сумма: {field('total')} ₽\n\n"
            f"👤 Клиент: @{message.from_user.username or message.from_user.id}\n"
            f"🆔 ID: {message.from_user.id}\n\n"
            f"📞 Телефон: {field('phone')}\n"
            f"📍 Улица: {field('street')}\n"
            f"🏠 Дом: {field('house')}\n"
            f"🚪 Подъезд: {field('entrance')}\n"
            f"🛗 Этаж: {field('floor')}\n"
            f"🚪 Квартира: {field('apartment')}\n\n"
            f"Статус: ⏳ В обработке (ждём оплату)"
        ),
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплата прошла", callback_data=f"pay:{oid}"),
         InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}")],
        [InlineKeyboardButton(text="💬 Связаться с клиентом", callback_data=f"contact:{oid}"),
         InlineKeyboardButton(text="📦 Заказ выдан", callback_data=f"done:{oid}")],
    ])
    try:
        sent = await bot.send_message(ADMIN_ID, orders[oid]["text"], parse_mode="HTML", reply_markup=kb)
        print("ЗАКАЗ ОТПРАВЛЕН АДМИНУ")
        try:
            await bot.pin_chat_message(ADMIN_ID, sent.message_id, disable_notification=True)
            print("ЗАКАЗ ЗАКРЕПЛЁН")
        except Exception as pe:
            print("НЕ УДАЛОСЬ ЗАКРЕПИТЬ:", pe)
        await message.answer(
            f"✅ Заказ #{oid} оформлен!\n"
            "Статус: ⏳ В обработке. Мы свяжемся с вами после подтверждения оплаты.",
            reply_markup=main_menu(),
        )
    except Exception as e:
        print("ОШИБКА ОТПРАВКИ:", e)


async def change_status(cb: CallbackQuery, oid: int, new_status: str):
    """Меняет строку «Статус: ...» на любую другую, не падая."""
    orders[oid]["text"] = re.sub(r"Статус: .*", f"Статус: {new_status}", orders[oid]["text"])
    try:
        await cb.message.edit_text(orders[oid]["text"], parse_mode="HTML")
    except Exception as e:
        print("ОШИБКА РЕДАКТИРОВАНИЯ:", e)


# ===== КНОПКИ АДМИНА ПО ЗАКАЗУ =====

@dp.callback_query(F.data.startswith("pay:"))
async def pay_ok(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    if oid not in orders:
        await cb.answer("Заказ не найден")
        return
    await change_status(cb, oid, "💰 Оплачен")
    kb_admin = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{oid}"),
         InlineKeyboardButton(text="📦 Заказ выдан", callback_data=f"done:{oid}")],
        [InlineKeyboardButton(text="💬 Связаться с клиентом", callback_data=f"contact:{oid}")],
    ])
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_admin)
    except Exception:
        pass
    await bot.send_message(orders[oid]["user_id"],
                           f"💰 Оплата заказа #{oid} подтверждена! Ожидайте доставку.")
    msg = await bot.send_message(orders[oid]["user_id"],
                                 f"Есть вопросы по заказу #{oid}? Напишите менеджеру.")
    orders[oid]["notice_id"] = msg.message_id
    kb2 = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать менеджеру", callback_data=f"chat:{oid}")],
    ])
    try:
        await bot.edit_message_reply_markup(chat_id=orders[oid]["user_id"],
                                            message_id=msg.message_id, reply_markup=kb2)
    except Exception:
        pass
    await cb.answer("Оплата подтверждена")


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_order(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    if oid not in orders:
        await cb.answer("Заказ не найден")
        return
    await change_status(cb, oid, "❌ Отменён")
    await remove_notice(oid)
    await bot.send_message(orders[oid]["user_id"],
                           f"❌ Заказ #{oid} отменён. Если это ошибка — напишите в поддержку.",
                           reply_markup=main_menu())
    await cb.answer("Заказ отменён")


@dp.callback_query(F.data.startswith("done:"))
async def order_done(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data.split(":")[1])
    if oid not in orders:
        await cb.answer("Заказ не найден")
        return

    await change_status(cb, oid, "📦 Выдан")

    await remove_notice(oid)

    uid = orders[oid]["user_id"]
    await state.clear()
    try:
        await bot.send_message(uid,
                               "Диалог с менеджером закрыт. Напишите /start, чтобы вернуться в меню.",
                               reply_markup=main_menu())
    except Exception as e:
        print("ОШИБКА ЗАКРЫТИЯ ДИАЛОГА:", e)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оставить отзыв менеджеру", url=MANAGER_URL)],
    ])
    try:
        await bot.send_message(uid,
                               f"🎉 Заказ #{oid} выдан! Спасибо за покупку!\n"
                               "Будем рады вашему отзыву — напишите нашему менеджеру:",
                               reply_markup=kb)
        print("УВЕДОМЛЕНИЕ О ВЫДАЧЕ ОТПРАВЛЕНО")
    except Exception as e:
        print("ОШИБКА ОТПРАВКИ УВЕДОМЛЕНИЯ:", e)

    await cb.answer("Выдано")


@dp.callback_query(F.data.startswith("contact:"))
async def contact_client(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data.split(":")[1])
    if oid not in orders:
        await cb.answer("Заказ не найден")
        return
    await state.set_state(States.admin_reply)
    await state.update_data(uid=orders[oid]["user_id"])
    await cb.message.answer(
        f"Режим ответа клиенту (заказ #{oid}). Пишите сообщения — "
        "они уйдут клиенту. Кнопка «Закрыть диалог» завершит переписку.",
        reply_markup=dialog_kb(),
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("chat:"))
async def chat_with_admin(cb: CallbackQuery, state: FSMContext):
    await state.set_state(States.user_chat)
    await cb.message.answer(
        "Вы пишете менеджеру. Сообщения уйдут напрямую.\n"
        "Кнопка «Закрыть диалог» завершит переписку.",
        reply_markup=dialog_kb(),
    )
    await cb.answer()


# ===== ДИАЛОГ ПОДДЕРЖКИ =====

@dp.message(F.text == "💬 Связаться с поддержкой")
async def support_enter(message: Message, state: FSMContext):
    await state.set_state(States.user_chat)
    await message.answer("Опишите ваш вопрос — мы ответим в этом чате.",
                         reply_markup=dialog_kb())


@dp.message(F.text == "🔒 Закрыть диалог")
async def close_dialog_user(message: Message, state: FSMContext):
    was_chat = await state.get_state() == States.user_chat
    await state.clear()
    for oid in list(orders):
        if orders[oid]["user_id"] == message.from_user.id:
            await remove_notice(oid)
    await message.answer("Диалог закрыт. Напишите /start, чтобы вернуться в меню.",
                         reply_markup=main_menu())
    if was_chat:
        await bot.send_message(ADMIN_ID, "Клиент закрыл диалог.")


@dp.message(States.user_chat)
async def user_to_admin(message: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID,
                           f"💬 Сообщение от клиента @{message.from_user.username or message.from_user.id}:",
                           reply_markup=admin_msg_kb(message.from_user.id))
    await message.copy_to(ADMIN_ID)
    await message.answer("Отправлено! Ждите ответа. Или нажмите «Закрыть диалог».")


@dp.callback_query(F.data.startswith("reply:"))
async def admin_reply_btn(cb: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_reply)
    await state.update_data(uid=int(cb.data.split(":")[1]))
    await cb.message.answer("Пишите ответ клиенту:", reply_markup=dialog_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("close_admin:"))
async def admin_close(cb: CallbackQuery, state: FSMContext):
    uid = int(cb.data.split(":")[1])
    await state.clear()
    for oid in list(orders):
        if orders[oid]["user_id"] == uid:
            await remove_notice(oid)
    await cb.message.answer("Диалог закрыт.")
    try:
        await bot.send_message(uid, "Менеджер закрыл диалог. Напишите /start, чтобы вернуться в меню.",
                               reply_markup=main_menu())
    except Exception:
        pass
    await cb.answer("Диалог закрыт")


@dp.message(States.admin_reply)
async def admin_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("uid")
    if not uid:
        await state.clear()
        return
    await message.copy_to(uid)
    await message.answer("Отправлено клиенту.")


# ===== ЗАПУСК =====

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
