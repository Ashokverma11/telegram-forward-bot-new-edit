from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
import sqlite3
import asyncio

API_TOKEN = "7595469262:AAE7oOPJu7DZieCdDE0vyc9_ADX7K8kTAnw"
if not API_TOKEN or not API_TOKEN.strip():
    raise ValueError("Invalid or missing API token! Please check your BotFather token.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def setup_db():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        destination_id INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1,
        allow_edits INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def add_sample_tasks():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()

    cursor.execute("INSERT INTO tasks (label, source_id, destination_id) VALUES (?, ?, ?)", 
                   ('Task 1', 101, 201))
    cursor.execute("INSERT INTO tasks (label, source_id, destination_id) VALUES (?, ?, ?)", 
                   ('Task 2', 102, 202))
    conn.commit()
    conn.close()

setup_db()

add_sample_tasks()

@dp.message(Command("start")) 
async def send_welcome(message: types.Message):
    await message.reply("Welcome! Use /settings to manage your tasks.")

@dp.message(Command("settings"))
async def show_settings(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Manage Forwarding Tasks", callback_data="manage_tasks")],
            [InlineKeyboardButton(text="Stop BOT", callback_data="stop_bot")],
            [InlineKeyboardButton(text="Disconnect Account", callback_data="disconnect")]
        ]
    )

    await message.reply("Settings Menu:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == 'manage_tasks')
async def manage_tasks(callback_query: types.CallbackQuery):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, label, is_active FROM tasks")
    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        await bot.answer_callback_query(callback_query.id, "No tasks found.")
        return
    inline_buttons = []
    for task in tasks:
        label = task[1]
        status = "\u2705" if task[2] else "\u274C"
        inline_buttons.append([InlineKeyboardButton(text=f"{status} {label}", callback_data=f"task_{task[0]}")])

    inline_buttons.append([InlineKeyboardButton(text="Back to Settings", callback_data="back_to_settings")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

    await bot.send_message(callback_query.from_user.id, "Select a task to modify:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('task_'))
async def task_options(callback_query: types.CallbackQuery):
    task_id = callback_query.data.split('_')[1] 
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, label, is_active FROM tasks WHERE id=?", (task_id,))
    task = cursor.fetchone()
    conn.close()

    if not task:
        await bot.answer_callback_query(callback_query.id, "Task not found.")
        return

    label = task[1]
    status = "Active" if task[2] else "Inactive"

    inline_buttons = [
        [InlineKeyboardButton(text=f"Toggle Status: {status}", callback_data=f"toggle_status_{task_id}")],
        [InlineKeyboardButton(text="Back to Tasks", callback_data="manage_tasks")]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

    await bot.send_message(callback_query.from_user.id, f"Task: {label}\nStatus: {status}", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == 'back_to_settings')
async def back_to_settings(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Manage Forwarding Tasks", callback_data="manage_tasks")],
            [InlineKeyboardButton(text="Stop BOT", callback_data="stop_bot")],
            [InlineKeyboardButton(text="Disconnect Account", callback_data="disconnect")]
        ]
    )
    await bot.send_message(callback_query.from_user.id, "Settings Menu:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('delete_'))
async def delete_task(callback_query: types.CallbackQuery):
    task_id = int(callback_query.data.split('_')[1])

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    await bot.answer_callback_query(callback_query.id, "Task deleted successfully.")
    await manage_tasks(callback_query)

@dp.callback_query(lambda c: c.data.startswith('toggle_'))
async def toggle_task(callback_query: types.CallbackQuery):
    data_parts = callback_query.data.split('_')
    if len(data_parts) > 2:
        task_id = int(data_parts[2])  # استخراج الـ task_id
    else:
        await bot.answer_callback_query(callback_query.id, "Invalid task ID.")
        return


    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET is_active = 1 - is_active WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    await bot.answer_callback_query(callback_query.id, "Task status updated.")
    await manage_tasks(callback_query)

@dp.callback_query(lambda c: c.data.startswith('edits_'))
async def toggle_edits(callback_query: types.CallbackQuery):
    task_id = int(callback_query.data.split('_')[1])

    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET allow_edits = 1 - allow_edits WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    await bot.answer_callback_query(callback_query.id, "Edit option updated.")
    await manage_tasks(callback_query)

@dp.callback_query(lambda c: c.data == 'stop_bot')
async def stop_bot(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id, "Stopping the bot...")
    await bot.send_message(callback_query.from_user.id, "The bot will stop now.")
    await dp.stop_polling()  # لإيقاف البوت
@dp.callback_query(lambda c: c.data == 'disconnect')
async def disconnect_account(callback_query: types.CallbackQuery):
    # هنا تقدر تضيف أي كود للفصل
    await bot.answer_callback_query(callback_query.id, "Disconnecting your account...")
    await bot.send_message(callback_query.from_user.id, "Your account has been disconnected.")

if __name__ == '__main__':
    try:
        asyncio.run(dp.start_polling(bot, skip_updates=True))
    except TelegramAPIError as e:
        print(f"Telegram API error: {e}")