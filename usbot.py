import logging
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook

TOKEN = "8463419754:AAH_4I1T-LZlgK331z9WL-cQ_WUw_5YHijY"

WEBHOOK_HOST = "https://bot-1-9qsl.onrender.com"
WEBHOOK_PATH = f"/webhook/{8463419754:AAH_4I1T-LZlgK331z9WL-cQ_WUw_5YHijY}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8000

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

DB = "anon_bot.db"

# Временные данные
temp = {}

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                text TEXT,
                created_at TEXT
            )
        """)
        await db.commit()

async def add_user(user: types.User):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users(user_id, username) VALUES(?, ?)",
            (user.id, user.username or "")
        )
        await db.commit()

async def get_users(exclude_id: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT user_id, username FROM users WHERE user_id != ?",
            (exclude_id,)
        )
        return await cursor.fetchall()

async def save_message(sender_id: int, receiver_id: int, text: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO messages(sender_id, receiver_id, text, created_at) VALUES(?, ?, ?, ?)",
            (sender_id, receiver_id, text, datetime.utcnow().isoformat())
        )
        await db.commit()

async def get_inbox(receiver_id: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT id, text, created_at FROM messages WHERE receiver_id = ? ORDER BY id DESC",
            (receiver_id,)
        )
        return await cursor.fetchall()

async def get_message(msg_id: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT sender_id, receiver_id, text FROM messages WHERE id = ?",
            (msg_id,)
        )
        return await cursor.fetchone()

# -------------------------
# Handlers
# -------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await add_user(message.from_user)
    await message.answer(
        "👋 Привет!\n\n"
        "📨 /send — отправить анонимное сообщение\n"
        "📥 /inbox — посмотреть входящие и ответить"
    )

@dp.message_handler(commands=["send"])
async def cmd_send(message: types.Message):
    users = await get_users(message.from_user.id)

    if not users:
        await message.answer("Пока нет других пользователей. Пусть кто-то сначала напишет /start.")
        return

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for user_id, username in users:
        label = username if username else str(user_id)
        keyboard.add(types.KeyboardButton(label))

    temp[message.from_user.id] = {"step": "choose_receiver", "users": users}
    await message.answer("Выбери получателя:", reply_markup=keyboard)

@dp.message_handler(commands=["inbox"])
async def cmd_inbox(message: types.Message):
    inbox = await get_inbox(message.from_user.id)

    if not inbox:
        await message.answer("У тебя пока нет входящих сообщений.")
        return

    text = "📥 Входящие:\n\n"
    for msg_id, msg_text, created in inbox[:10]:
        text += f"ID {msg_id}: {msg_text[:40]}...\n"

    text += "\nНапиши ID сообщения, чтобы ответить."
    temp[message.from_user.id] = {"step": "choose_message"}
    await message.answer(text)

@dp.message_handler()
async def all_messages_handler(message: types.Message):
    user_id = message.from_user.id
# если пользователь не в процессе — ничего не делаем
    if user_id not in temp:
        return

    state = temp[user_id]["step"]

    # Шаг 1: выбор получателя
    if state == "choose_receiver":
        users = temp[user_id]["users"]
        text = message.text.strip()

        receiver_id = None
        if text.isdigit():
            receiver_id = int(text)
        else:
            for uid, uname in users:
                if uname == text:
                    receiver_id = uid
                    break

        if not receiver_id:
            await message.answer("Не удалось найти пользователя. Попробуй /send снова.")
            temp.pop(user_id, None)
            return

        temp[user_id] = {"step": "write_message", "receiver_id": receiver_id}
        await message.answer("Напиши сообщение:")

    # Шаг 2: написание сообщения
    elif state == "write_message":
        receiver_id = temp[user_id]["receiver_id"]
        await save_message(user_id, receiver_id, message.text)

        await bot.send_message(
            receiver_id,
            f"📩 *Анонимное сообщение:*\n\n{message.text}",
            parse_mode="Markdown"
        )

        await message.answer("Сообщение отправлено анонимно ✅", reply_markup=types.ReplyKeyboardRemove())
        temp.pop(user_id, None)

    # Шаг 3: выбор сообщения для ответа
    elif state == "choose_message":
        if not message.text.isdigit():
            await message.answer("Нужно ввести ID сообщения цифрами.")
            return

        msg_id = int(message.text)
        row = await get_message(msg_id)

        if not row:
            await message.answer("Сообщение не найдено.")
            temp.pop(user_id, None)
            return

        sender_id, receiver_id, msg_text = row

        if receiver_id != user_id:
            await message.answer("Это не твоё сообщение.")
            temp.pop(user_id, None)
            return

        temp[user_id] = {"step": "write_reply", "sender_id": sender_id}
        await message.answer("Напиши ответ:")

    # Шаг 4: отправка ответа
    elif state == "write_reply":
        sender_id = temp[user_id]["sender_id"]

        await bot.send_message(
            sender_id,
            f"📨 *Ответ на твоё анонимное сообщение:*\n\n{message.text}",
            parse_mode="Markdown"
        )

        await message.answer("Ответ отправлен анонимно ✅")
        temp.pop(user_id, None)

# -------------------------
# Webhook setup
# -------------------------
async def on_startup(dp):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )




