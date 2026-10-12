import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
ADMIN_IDS      = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
BANK_NAME      = os.getenv("BANK_NAME", "Monobank")
CARD_NUMBER    = os.getenv("CARD_NUMBER", "4441111009513544")
CARD_HOLDER    = os.getenv("CARD_HOLDER", "Ivan Petrenko")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "₴")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ═══════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════
def get_conn():
    return sqlite3.connect("shop.db", check_same_thread=False)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, description TEXT,
        price INTEGER NOT NULL, duration TEXT NOT NULL,
        category TEXT DEFAULT 'Основное', active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL, key_value TEXT NOT NULL,
        used INTEGER DEFAULT 0, used_by INTEGER, used_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, username TEXT,
        product_id INTEGER NOT NULL, product_name TEXT,
        amount INTEGER NOT NULL, status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        confirmed_at TEXT, key_given TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        registered_at TEXT DEFAULT (datetime('now')))""")
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO products (name, description, price, duration, category) VALUES (?,?,?,?,?)",
            [
                ("ULTIMA iOS","Мощный чит для iOS. Без бана, быстрая установка.",130,"1 день","iOS"),
                ("ULTIMA iOS","Мощный чит для iOS. Без бана, быстрая установка.",600,"7 дней","iOS"),
                ("ULTIMA iOS","Мощный чит для iOS. Без бана, быстрая установка.",1800,"30 дней","iOS"),
                ("ULTIMA Android","Версия для Android с теми же функциями.",100,"1 день","Android"),
                ("ULTIMA Android","Версия для Android с теми же функциями.",500,"7 дней","Android"),
                ("ULTIMA PC","Полный функционал для PC/Windows.",200,"1 день","PC"),
                ("ULTIMA PC","Полный функционал для PC/Windows.",900,"7 дней","PC"),
            ]
        )
    conn.commit(); conn.close()

def db_get_categories():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products WHERE active=1")
    r = [row[0] for row in c.fetchall()]; conn.close(); return r

def db_get_products_by_category(cat):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM products WHERE category=? AND active=1", (cat,))
    r = c.fetchall(); conn.close(); return r

def db_get_product(pid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id=?", (pid,))
    r = c.fetchone(); conn.close(); return r

def db_get_all_products():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM products ORDER BY category, price")
    r = c.fetchall(); conn.close(); return r

def db_add_product(name, desc, price, duration, cat):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO products (name,description,price,duration,category) VALUES (?,?,?,?,?)",
              (name, desc, price, duration, cat))
    pid = c.lastrowid; conn.commit(); conn.close(); return pid

def db_add_key(product_id, key_value):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO keys (product_id, key_value) VALUES (?,?)", (product_id, key_value))
    conn.commit(); conn.close()

def db_get_free_key(product_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, key_value FROM keys WHERE product_id=? AND used=0 LIMIT 1", (product_id,))
    r = c.fetchone(); conn.close(); return r

def db_use_key(key_id, user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE keys SET used=1, used_by=?, used_at=datetime('now') WHERE id=?", (user_id, key_id))
    conn.commit(); conn.close()

def db_count_free_keys(product_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM keys WHERE product_id=? AND used=0", (product_id,))
    r = c.fetchone()[0]; conn.close(); return r

def db_create_order(user_id, username, product_id, product_name, amount):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO orders (user_id,username,product_id,product_name,amount) VALUES (?,?,?,?,?)",
              (user_id, username, product_id, product_name, amount))
    oid = c.lastrowid; conn.commit(); conn.close(); return oid

def db_get_order(order_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    r = c.fetchone(); conn.close(); return r

def db_confirm_order(order_id, key_given):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE orders SET status='confirmed', confirmed_at=datetime('now'), key_given=? WHERE id=?",
              (key_given, order_id))
    conn.commit(); conn.close()

def db_reject_order(order_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
    conn.commit(); conn.close()

def db_get_pending_orders():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status='pending' ORDER BY created_at DESC")
    r = c.fetchall(); conn.close(); return r

def db_get_user_orders(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (user_id,))
    r = c.fetchall(); conn.close(); return r

def db_register_user(user_id, username, full_name):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id,username,full_name) VALUES (?,?,?)",
              (user_id, username, full_name))
    conn.commit(); conn.close()

def db_get_stats():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'"); confirmed = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM orders WHERE status='confirmed'"); revenue = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'"); pending = c.fetchone()[0]
    conn.close(); return users, confirmed, revenue, pending

# ═══════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════
def kb_main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Каталог"), KeyboardButton(text="📋 Мои заказы")],
        [KeyboardButton(text="💬 Поддержка"), KeyboardButton(text="ℹ️ О нас")],
    ], resize_keyboard=True)

def kb_admin_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📦 Заказы")],
        [KeyboardButton(text="🗝 Добавить ключи"), KeyboardButton(text="➕ Добавить товар")],
        [KeyboardButton(text="🛒 Каталог")],
    ], resize_keyboard=True)

def kb_categories(categories):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📁 {cat}", callback_data=f"cat_{cat}")]
        for cat in categories
    ])

def kb_products(products):
    buttons = [
        [InlineKeyboardButton(text=f"⏱ {p[4]} — {p[3]} {CURRENCY_SYMBOL}", callback_data=f"product_{p[0]}")]
        for p in products
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_cats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_product_detail(product_id, category):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_{category}")],
    ])

def kb_payment(order_id, card):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать карту", callback_data=f"copy_{card}")],
        [InlineKeyboardButton(text="✅ Я оплатил — отправить чек", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{order_id}")],
    ])

def kb_admin_order(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}"),
    ]])

def kb_back_to_cats():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В каталог", callback_data="back_to_cats")]
    ])

# ═══════════════════════════════════════════
#  STATES
# ═══════════════════════════════════════════
class OrderState(StatesGroup):
    waiting_receipt = State()

class AddKeyState(StatesGroup):
    choose_product = State()
    enter_keys = State()

class AddProductState(StatesGroup):
    name = State()
    description = State()
    price = State()
    duration = State()
    category = State()

# ═══════════════════════════════════════════
#  ROUTER
# ═══════════════════════════════════════════
router = Router()

def is_admin(uid): return uid in ADMIN_IDS

# ── /start ────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message):
    db_register_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"🔑 Добро пожаловать в <b>ANONYM KEYS</b>\n\n"
        f"Мы продаём лицензионные ключи и подписки.\n"
        f"Выбери раздел в меню ниже 👇",
        parse_mode="HTML", reply_markup=kb_main_menu()
    )

# ── Каталог ───────────────────────────────
@router.message(F.text == "🛒 Каталог")
async def show_catalog(message: Message):
    cats = db_get_categories()
    if not cats:
        await message.answer("😔 Каталог пуст. Скоро добавим товары!"); return
    await message.answer("📁 <b>Выбери категорию:</b>", parse_mode="HTML", reply_markup=kb_categories(cats))

@router.callback_query(F.data == "back_to_cats")
async def back_to_cats(call: CallbackQuery):
    cats = db_get_categories()
    await call.message.edit_text("📁 <b>Выбери категорию:</b>", parse_mode="HTML", reply_markup=kb_categories(cats))

@router.callback_query(F.data.startswith("cat_"))
async def show_category(call: CallbackQuery):
    cat = call.data[4:]
    products = db_get_products_by_category(cat)
    if not products:
        await call.answer("Нет доступных товаров", show_alert=True); return
    desc = products[0][2]
    await call.message.edit_text(
        f"📦 <b>{cat}</b>\n\n{desc}\n\n✅ Без бана\n⚡ Быстрая установка\n🔄 Регулярные обновления\n\n⏳ <b>Выбери тариф:</b>",
        parse_mode="HTML", reply_markup=kb_products(products)
    )

@router.callback_query(F.data.startswith("product_"))
async def show_product(call: CallbackQuery):
    pid = int(call.data[8:])
    p = db_get_product(pid)
    if not p:
        await call.answer("Товар не найден", show_alert=True); return
    pid, name, desc, price, duration, cat, active = p
    free = db_count_free_keys(pid)
    stock = f"✅ В наличии: {free} шт." if free > 0 else "❌ Нет в наличии"
    await call.message.edit_text(
        f"🔑 <b>{name}</b>\n━━━━━━━━━━━━━━━━━\n"
        f"⏱ Тариф: <b>{duration}</b>\n💰 Цена: <b>{price} {CURRENCY_SYMBOL}</b>\n{stock}\n"
        f"━━━━━━━━━━━━━━━━━\n📝 {desc}",
        parse_mode="HTML", reply_markup=kb_product_detail(pid, cat)
    )

# ── Покупка ───────────────────────────────
@router.callback_query(F.data.startswith("buy_"))
async def buy_product(call: CallbackQuery, state: FSMContext):
    pid = int(call.data[4:])
    p = db_get_product(pid)
    if not p:
        await call.answer("Товар не найден", show_alert=True); return
    pid, name, desc, price, duration, cat, active = p
    username = call.from_user.username or str(call.from_user.id)
    order_id = db_create_order(call.from_user.id, username, pid, f"{name} ({duration})", price)
    await state.set_state(OrderState.waiting_receipt)
    await state.update_data(order_id=order_id, product_id=pid)
    await call.message.edit_text(
        f"💳 <b>Оплата гривнями</b>\n━━━━━━━━━━━━━━━━━\n"
        f"🛒 Товар: <b>{name}</b>\n⏱ Тариф: <b>{duration}</b>\n💰 До оплаты: <b>{price} {CURRENCY_SYMBOL}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n🏦 Банк: <b>{BANK_NAME}</b>\n💳 Карта: <code>{CARD_NUMBER}</code>\n"
        f"👤 Получатель: <b>{CARD_HOLDER}</b>\n━━━━━━━━━━━━━━━━━\n"
        f"📎 Переведите <b>точную сумму</b> и нажмите\n«Я оплатил» — отправьте чек (фото/PDF).",
        parse_mode="HTML", reply_markup=kb_payment(order_id, CARD_NUMBER)
    )

@router.callback_query(F.data.startswith("copy_"))
async def copy_card(call: CallbackQuery):
    card = call.data[5:]
    await call.answer(f"Карта: {card}", show_alert=True)

@router.callback_query(F.data.startswith("cancel_"))
async def cancel_order(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data[7:])
    db_reject_order(order_id)
    await state.clear()
    await call.message.edit_text("❌ Заказ отменён.\n\nВозвращайся, когда будешь готов! 👋", reply_markup=kb_back_to_cats())

@router.callback_query(F.data.startswith("paid_"))
async def user_paid(call: CallbackQuery):
    await call.message.answer("📸 Отправьте чек оплаты:\n<i>(фото, PDF или скриншот)</i>", parse_mode="HTML")
    await call.answer()

async def notify_admins(bot: Bot, message: Message, order, receipt_type: str):
    oid, uid, uname, pid, pname, amount, *_ = order
    ulink = f"@{uname}" if uname else f"<a href='tg://user?id={uid}'>Пользователь</a>"
    text = (
        f"🔔 <b>Новый чек на оплату!</b>\n━━━━━━━━━━━━━━━━━\n"
        f"📋 Заказ: <b>#{oid}</b>\n👤 {ulink} (<code>{uid}</code>)\n"
        f"🛒 Товар: <b>{pname}</b>\n💰 Сумма: <b>{amount} {CURRENCY_SYMBOL}</b>\n"
        f"📎 Тип чека: {receipt_type}\n━━━━━━━━━━━━━━━━━"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.forward(admin_id)
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=kb_admin_order(oid))
        except Exception as e:
            print(f"Не удалось уведомить admin {admin_id}: {e}")

@router.message(OrderState.waiting_receipt, F.photo)
async def receipt_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order = db_get_order(data.get("order_id"))
    if not order:
        await state.clear(); return
    await notify_admins(bot, message, order, "фото")
    await state.clear()
    await message.answer("✅ <b>Чек получен!</b>\n\nМы проверяем оплату — ключ придёт в течение нескольких минут.\nСпасибо за ожидание! 🙏", parse_mode="HTML")

@router.message(OrderState.waiting_receipt, F.document)
async def receipt_doc(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order = db_get_order(data.get("order_id"))
    if not order:
        await state.clear(); return
    await notify_admins(bot, message, order, "документ")
    await state.clear()
    await message.answer("✅ <b>Чек получен!</b>\n\nМы проверяем оплату — ключ придёт в течение нескольких минут.\nСпасибо за ожидание! 🙏", parse_mode="HTML")

# ── Мои заказы ────────────────────────────
@router.message(F.text == "📋 Мои заказы")
async def my_orders(message: Message):
    orders = db_get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("📭 У тебя пока нет заказов.\n\nЗагляни в каталог! 🛒"); return
    status_map = {"pending": "⏳ Ожидает", "confirmed": "✅ Выполнен", "rejected": "❌ Отклонён"}
    text = "📋 <b>Твои последние заказы:</b>\n\n"
    for o in orders:
        oid, uid, uname, pid, pname, amount, status, created, confirmed, key = o
        text += f"#{oid} | {pname} | {amount} {CURRENCY_SYMBOL} | {status_map.get(status, status)}\n"
        if status == "confirmed" and key:
            text += f"   🔑 Ключ: <code>{key}</code>\n"
        text += "\n"
    await message.answer(text, parse_mode="HTML")

# ── Поддержка ─────────────────────────────
@router.message(F.text == "💬 Поддержка")
async def support(message: Message):
    await message.answer("💬 <b>Поддержка</b>\n\nЕсли возникли вопросы — напиши администратору напрямую.\nИли используй /help с описанием проблемы.", parse_mode="HTML")

# ── О нас ─────────────────────────────────
@router.message(F.text == "ℹ️ О нас")
async def about(message: Message):
    await message.answer(
        "🔑 <b>ANONYM KEYS</b>\n\nНадёжный магазин цифровых ключей и подписок.\n\n"
        "✅ <b>Наши гарантии:</b>\n• Без бана — 100% безопасно\n• Быстрая выдача после оплаты\n"
        "• Поддержка 24/7\n• Регулярные обновления\n\n💎 Работаем с 2023 года",
        parse_mode="HTML"
    )

# ══════════════════════════════════════════
#  ADMIN HANDLERS
# ══════════════════════════════════════════
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id): return
    users, confirmed, revenue, pending = db_get_stats()
    await message.answer(
        f"🔐 <b>Панель администратора</b>\n\n👥 Пользователей: <b>{users}</b>\n"
        f"✅ Выполнено заказов: <b>{confirmed}</b>\n💰 Выручка: <b>{revenue} {CURRENCY_SYMBOL}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>",
        parse_mode="HTML", reply_markup=kb_admin_menu()
    )

@router.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id): return
    users, confirmed, revenue, pending = db_get_stats()
    await message.answer(
        f"📊 <b>Статистика</b>\n\n👥 Пользователей: <b>{users}</b>\n✅ Выполнено: <b>{confirmed}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n💰 Выручка: <b>{revenue} {CURRENCY_SYMBOL}</b>",
        parse_mode="HTML"
    )

@router.message(F.text == "📦 Заказы")
async def admin_orders(message: Message):
    if not is_admin(message.from_user.id): return
    orders = db_get_pending_orders()
    if not orders:
        await message.answer("✅ Нет ожидающих заказов!"); return
    for o in orders:
        oid, uid, uname, pid, pname, amount, status, created, confirmed, key = o
        ulink = f"@{uname}" if uname else f"ID:{uid}"
        await message.answer(
            f"📋 Заказ <b>#{oid}</b>\n👤 {ulink} (<code>{uid}</code>)\n🛒 {pname}\n💰 {amount} {CURRENCY_SYMBOL}\n🕐 {created}",
            parse_mode="HTML", reply_markup=kb_admin_order(oid)
        )

@router.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True); return
    order_id = int(call.data[8:])
    order = db_get_order(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True); return
    oid, uid, uname, pid, pname, amount, status, *_ = order
    if status != "pending":
        await call.answer("Уже обработан!", show_alert=True); return
    key_row = db_get_free_key(pid)
    if key_row:
        key_id, key_value = key_row
        db_use_key(key_id, uid)
        db_confirm_order(order_id, key_value)
        try:
            await bot.send_message(uid,
                f"✅ <b>Оплата подтверждена!</b>\n\n🛒 Товар: <b>{pname}</b>\n━━━━━━━━━━━━━━━━━\n"
                f"🔑 Твой ключ:\n<code>{key_value}</code>\n━━━━━━━━━━━━━━━━━\n✨ Спасибо за покупку!",
                parse_mode="HTML")
        except Exception as e:
            print(f"Не удалось отправить ключ: {e}")
        await call.message.edit_text(f"✅ <b>Заказ #{order_id} подтверждён.</b>\nКлюч отправлен.", parse_mode="HTML")
        await call.answer("✅ Подтверждено!")
    else:
        db_confirm_order(order_id, "вручную")
        try:
            await bot.send_message(uid, f"✅ <b>Оплата подтверждена!</b>\n\n🛒 {pname}\n\n⏳ Ключ выдаётся вручную — ожидай.", parse_mode="HTML")
        except: pass
        await call.message.edit_text(f"⚠️ Заказ #{order_id} подтверждён, но <b>ключей нет!</b>\nВыдай вручную пользователю <code>{uid}</code>.", parse_mode="HTML")
        await call.answer("⚠️ Ключей нет!", show_alert=True)

@router.callback_query(F.data.startswith("reject_"))
async def reject_order(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True); return
    order_id = int(call.data[7:])
    order = db_get_order(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True); return
    oid, uid, uname, pid, pname, amount, status, *_ = order
    if status != "pending":
        await call.answer("Уже обработан!", show_alert=True); return
    db_reject_order(order_id)
    try:
        await bot.send_message(uid, f"❌ <b>Оплата не подтверждена</b>\n\nЗаказ: <b>{pname}</b>\n\nЕсли оплатили — обратитесь в поддержку /help", parse_mode="HTML")
    except: pass
    await call.message.edit_text(f"❌ <b>Заказ #{order_id} отклонён.</b>", parse_mode="HTML")
    await call.answer("❌ Отклонено")

@router.message(F.text == "🗝 Добавить ключи")
async def add_keys_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    products = db_get_all_products()
    if not products:
        await message.answer("Нет товаров!"); return
    text = "📦 <b>Введи ID товара:</b>\n\n"
    for p in products:
        pid, name, desc, price, duration, cat, active = p
        free = db_count_free_keys(pid)
        text += f"{pid}. {'✅' if active else '❌'} {name} ({duration}) — {price} {CURRENCY_SYMBOL} | 🗝 {free} шт.\n"
    await message.answer(text, parse_mode="HTML")
    await state.set_state(AddKeyState.choose_product)

@router.message(AddKeyState.choose_product)
async def add_keys_choose(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        pid = int(message.text.strip())
    except ValueError:
        await message.answer("Введи числовой ID"); return
    p = db_get_product(pid)
    if not p:
        await message.answer("Товар не найден"); return
    await state.update_data(product_id=pid, product_name=p[1])
    await state.set_state(AddKeyState.enter_keys)
    await message.answer(f"🗝 Ключи для: <b>{p[1]} ({p[4]})</b>\n\nВведи ключи <b>каждый с новой строки</b>:", parse_mode="HTML")

@router.message(AddKeyState.enter_keys)
async def add_keys_enter(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    keys = [k.strip() for k in message.text.strip().split("\n") if k.strip()]
    for key in keys:
        db_add_key(data["product_id"], key)
    await state.clear()
    await message.answer(f"✅ Добавлено <b>{len(keys)}</b> ключей для <b>{data['product_name']}</b>!", parse_mode="HTML")

@router.message(F.text == "➕ Добавить товар")
async def add_product_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(AddProductState.name)
    await message.answer("📦 Введи название товара:")

@router.message(AddProductState.name)
async def ap_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProductState.description)
    await message.answer("📝 Введи описание:")

@router.message(AddProductState.description)
async def ap_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProductState.price)
    await message.answer("💰 Введи цену (число):")

@router.message(AddProductState.price)
async def ap_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
    except ValueError:
        await message.answer("Введи число!"); return
    await state.update_data(price=price)
    await state.set_state(AddProductState.duration)
    await message.answer("⏱ Введи тариф (например: 1 день, 7 дней):")

@router.message(AddProductState.duration)
async def ap_duration(message: Message, state: FSMContext):
    await state.update_data(duration=message.text.strip())
    await state.set_state(AddProductState.category)
    await message.answer("📁 Введи категорию (iOS / Android / PC):")

@router.message(AddProductState.category)
async def ap_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    data = await state.get_data()
    pid = db_add_product(data["name"], data["description"], data["price"], data["duration"], data["category"])
    await state.clear()
    await message.answer(
        f"✅ <b>Товар добавлен! ID: {pid}</b>\n\n{data['name']} ({data['duration']}) — {data['price']} {CURRENCY_SYMBOL}\nКатегория: {data['category']}\n\nДобавь ключи через «🗝 Добавить ключи»",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
