import logging
import aiosqlite
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook

TOKEN = "8463419754:AAH_4I1T-LZlgK331z9WL-cQ_WUw_5YHijY"

WEBHOOK_HOST = "https://YOUR_RENDER_URL"  # позже заменим на URL Render
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8000

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

DB = "anon_bot.db"

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

    await message.answer("Выбери получателя:", reply_markup=keyboard)

    @dp.message_handler(lambda msg: msg.text is not None)
    async def choose_receiver(msg: types.Message):
        text = msg.text.strip()
        receiver_id = None

        if text.isdigit():
            receiver_id = int(text)
        else:
            for uid, uname in users:
                if uname == text:
                    receiver_id = uid
                    break

        if not receiver_id:
            await msg.answer("Не удалось найти пользователя. Попробуй снова /send.")
            return

        await msg.answer("Напиши сообщение:")

        @dp.message_handler(lambda m: m.text is not None)
        async def send_anonymous(m: types.Message):
await save_message(m.from_user.id, receiver_id, m.text)

            await bot.send_message(
                receiver_id,
                f"📩 *Анонимное сообщение:*\n\n{m.text}",
                parse_mode="Markdown"
            )

            await m.answer("Сообщение отправлено анонимно ✅")
            await m.reply("Готово", reply_markup=types.ReplyKeyboardRemove())

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
    await message.answer(text)

    @dp.message_handler(lambda msg: msg.text and msg.text.isdigit())
    async def choose_message(msg: types.Message):
        msg_id = int(msg.text)
        row = await get_message(msg_id)

        if not row:
            await msg.answer("Сообщение не найдено.")
            return

        sender_id, receiver_id, msg_text = row

        if receiver_id != msg.from_user.id:
            await msg.answer("Это не твоё сообщение.")
            return

        await msg.answer("Напиши ответ:")

        @dp.message_handler(lambda m: m.text is not None)
        async def send_reply(m: types.Message):
            await bot.send_message(
                sender_id,
                f"📨 *Ответ на твоё анонимное сообщение:*\n\n{m.text}",
                parse_mode="Markdown"
            )
            await m.answer("Ответ отправлен анонимно ✅")

# -------------------------
# Webhook setup
# -------------------------
async def on_startup(dp):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if name == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
