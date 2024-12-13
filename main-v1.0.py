import sqlite3 , os , time
from telethon import TelegramClient, events
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext , MessageHandler, filters, CallbackContext
import asyncio
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import InputPeerChannel, InputPeerChat
from telethon.tl.functions.channels import LeaveChannelRequest, JoinChannelRequest
from telegram import Bot
from telegram import Update
from telethon.errors import SessionPasswordNeededError
import os
from dotenv import load_dotenv
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERNAME = os.getenv("ALLOWED_USERNAME")

user_chat_id = None
user_session_name = None
awaiting_number = False
awaiting_code = False
user_phone = None
user_code = None
awaiting_password = False

async def restricted_access(update: Update):
    """Check if the user is allowed to use the bot."""
    user = update.effective_user
    # if user.username != ALLOWED_USERNAME:
    #     await update.message.reply_text("Sorry, you are not authorized to use this bot.")
    #     return False
    return True

async def fetch_group_entity(link):
    try:
        group_entity = await client.get_entity(link)
        print(f"Fetched group entity: {group_entity.title}")
        return group_entity
    except Exception as e:
        print(f"Error fetching group entity: {e}")
        return None

def init_db():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        source_id INTEGER,
                        destination_id INTEGER,
                        enabled INTEGER DEFAULT 1,
                        edit_enabled INTEGER DEFAULT 1
                    )''')
    conn.commit()
    conn.close()

def add_task(name, source_id, destination_id):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO tasks (name, source_id, destination_id) VALUES (?, ?, ?)', (name, source_id, destination_id))
    conn.commit()
    conn.close()

def get_tasks():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def update_task(task_id, enabled=None, edit_enabled=None):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    if enabled is not None:
        cursor.execute('UPDATE tasks SET enabled = ? WHERE id = ?', (enabled, task_id))
    if edit_enabled is not None:
        cursor.execute('UPDATE tasks SET edit_enabled = ? WHERE id = ?', (edit_enabled, task_id))
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

client = TelegramClient('user_session', API_ID, API_HASH)

async def forward_messages():
    print("[+] Entered the Forward Messages Function")

    active_tasks = {}

    async def handle_new_message(event, destination_id):
        try:
            print(f"New message in {event.chat_id}: {event.message.text}")
            destination_entity = await client.get_entity(destination_id)
            await client.forward_messages(destination_entity, event.message)
            print(f"Message forwarded to Destination ID: {destination_id}")
        except Exception as e:
            print(f"Error forwarding message: {e}")

    while True:
        tasks = get_tasks()
        current_task_ids = {task[0] for task in tasks}

        for task_id in list(active_tasks.keys()):
            task = next((t for t in tasks if t[0] == task_id), None)
            if not task or not task[4]: 
                print(f"Removing event handler for Task ID: {task_id}")
                client.remove_event_handler(active_tasks[task_id]['handler'])
                del active_tasks[task_id]

        for task in tasks:
            task_id, name, source_id, destination_id, enabled, edit_enabled = task

            if enabled and task_id not in active_tasks:
                try:
                    try:
                        source_entity = await client.get_entity(source_id)
                        participants = await client.get_participants(source_entity)
                        if not any(p.is_self for p in participants):
                            raise ValueError("Not a member of the channel")
                    except Exception as e:
                        print(f"Task ID {task_id}: Not a member of the source channel. Disabling task.")
                        update_task(task_id, enabled=0)
                        error_message = (
                            f"⚠️ Task '{name}' has been disabled.\n"
                            f"Reason: You are not a member of the source channel (ID: {source_id}).\n"
                            f"Please join the channel manually and re-enable the task."
                        )
                        bot = Bot(token=BOT_TOKEN)
                        await bot.send_message(chat_id=user_chat_id, text=error_message)
                        continue

                    print(f"Listening for new messages from Source: {source_entity.title or source_entity.id}")
                    handler = lambda event: handle_new_message(event, destination_id)
                    client.add_event_handler(
                        handler,
                        events.NewMessage(chats=source_entity.id)
                    )
                    active_tasks[task_id] = {'source_id': source_id, 'destination_id': destination_id, 'handler': handler}
                except Exception as e:
                    print(f"Error setting up listener for Task ID {task_id}: {e}")

        await asyncio.sleep(10)

async def start(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id
    await update.message.reply_text(f"Welcome to the Forward Bot! Use /help to see available commands...\nYour Chat ID: {user_chat_id}")

async def add_forward(update: Update, context: CallbackContext):

    global user_chat_id
    user_chat_id = update.effective_chat.id
    args = context.args

    if len(args) == 5 and args[3] == "->":
        try:
            name = args[1]
            source_id = int(args[2])  
            destination_id = int(args[4]) 

            if isinstance(source_id, int) and isinstance(destination_id, int):
                add_task(name, source_id, destination_id)
                await update.message.reply_text(f"Forward task '{name}' added successfully!")
            else:
                await update.message.reply_text("Source ID and Destination ID must be numeric.")
        except ValueError:
            await update.message.reply_text("Invalid input! Make sure to use numeric IDs for source and destination.")
    else:
        await update.message.reply_text("Usage: /forward add NameLabel source_id -> destination_id")

async def manage_tasks(update: Update, context: CallbackContext):
    tasks = get_tasks()
    keyboard = []
    for task in tasks:
        task_id, name, _, _, enabled, _ = task
        status = "Enabled" if enabled else "Disabled"
        keyboard.append([InlineKeyboardButton(f"{name} ({status})", callback_data=f"manage_{task_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Manage Forwarding Tasks:", reply_markup=reply_markup)

async def get_channels(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id

    try:
        dialogs = await client.get_dialogs()

        response = "📋 All Channels :\n\n"
        for dialog in dialogs:
            if dialog.is_channel:
                try:
                    name = dialog.name or "Unnamed"
                    chat_id = dialog.entity.id
                    response += f"{name} -> {chat_id}\n"
                except:
                    chat_id = dialog.entity.id
                    response += f"{chat_id}\n"  
                
        MAX_LENGTH = 4000
        if len(response) > MAX_LENGTH:
            parts = [response[i:i + MAX_LENGTH] for i in range(0, len(response), MAX_LENGTH)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"Error fetching channels: {e}")

async def task_action(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id

    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("manage_"):
        task_id = int(data.split("_")[1])
        tasks = {task[0]: task[1] for task in get_tasks()} 
        task_name = tasks.get(task_id, "Unknown Task")
        keyboard = [
            [InlineKeyboardButton("Enable", callback_data=f"enable_{task_id}"), InlineKeyboardButton("Disable", callback_data=f"disable_{task_id}")],
            [InlineKeyboardButton("Delete", callback_data=f"delete_{task_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Task Actions for '{task_name}':", reply_markup=reply_markup)
    elif data.startswith("enable_"):
        task_id = int(data.split("_")[1])
        update_task(task_id, enabled=1)
        await query.edit_message_text(f"Task enabled.")
    elif data.startswith("disable_"):
        task_id = int(data.split("_")[1])
        update_task(task_id, enabled=0)
        await query.edit_message_text(f"Task disabled.")
    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        tasks = {task[0]: task[1] for task in get_tasks()}
        task_name = tasks.get(task_id, "Unknown Task")
        delete_task(task_id)
        await query.edit_message_text(f"Task '{task_name}' deleted.")

async def connect_number(update: Update, context: CallbackContext):
    global user_chat_id, awaiting_number
    if not await restricted_access(update):
        return

    user_chat_id = update.effective_chat.id
    user_session_name = f"session_{user_chat_id}"
    awaiting_number = True
    await update.message.reply_text(f"Welcome! Please enter your mobile number:")

async def handle_message(update: Update, context: CallbackContext):
    global user_chat_id, awaiting_number, awaiting_code, awaiting_password, user_phone, user_code , password
    if not await restricted_access(update):
        return

    text = update.message.text
    if ' password ' in str(password):
        text , password = text.split(' password ')
    if awaiting_number:
        user_phone = text
        try:
            await client.send_code_request(phone=user_phone)
            awaiting_number = False
            awaiting_code = True
            print('[+] Success Send To Number:',user_phone)
            await update.message.reply_text("Code sent! Please enter the verification code:")
        except Exception as e:
            await update.message.reply_text(f"Error sending code: {e}")

    elif awaiting_code:
        user_code = text
        try:
            # Attempt to sign in with the code
            await client.sign_in(phone=user_phone, code=user_code,password=password)
            awaiting_code = False
            print('[+] You have been successfully authenticated',user_phone)
            await update.message.reply_text("You have been successfully authenticated!")
        except SessionPasswordNeededError:
            # Handle 2FA scenario
            awaiting_code = False
            awaiting_password = True
            await update.message.reply_text("This account is protected by a 2FA password. Please enter your password:")

    elif awaiting_password:
        try:
            await client.sign_in(password=text)
            awaiting_password = False
            print('[+] You have successfully logged in with 2FA',user_phone)
            await update.message.reply_text("You have successfully logged in with 2FA!")
        except Exception as e:
            await update.message.reply_text(f"Error during password authentication: {e}")

async def check_connection(update: Update, context: CallbackContext):
    """Check if the client is connected to Telegram and display account info."""
    if not await restricted_access(update):
        return
    if client.is_connected():
        # Fetch account info if already connected
        try:
            account_info = await client.get_me()
            account_name = account_info.first_name
            account_username = account_info.username

            await update.message.reply_text(
                f"The client is already connected!\n"
                f"Current account details:\n"
                f"Name: {account_name}\n"
                f"Username: @{account_username if account_username else 'No username set'}"
            )
        except:
            await update.message.reply_text(
                f"The client is offline Please Write `\connect` To Connect Again!\n"
            )
    else:
        await update.message.reply_text("The client is not connected. Attempting to connect...")
        try:
            await client.connect()
            try:    
                # Fetch account info after connecting
                account_info = await client.get_me()
                account_name = account_info.first_name
                account_username = account_info.username

                await update.message.reply_text(
                    f"Client connected successfully!\n"
                    f"Current account details:\n"
                    f"Name: {account_name}\n"
                    f"Username: @{account_username if account_username else 'No username set'}"
                )
            except:
                await update.message.reply_text(
                    f"The client is offline Please Write `\connect` To Connect Again!\n"
                )

        except Exception as e:
            await update.message.reply_text(f"Failed to connect the client: {e}")

async def start_bot():
    global user_chat_id , password
    user_chat_id = None
    password = None
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_connection", check_connection))
    application.add_handler(CommandHandler("connect", connect_number))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("forward", add_forward))
    application.add_handler(CommandHandler("manage", manage_tasks))
    application.add_handler(CommandHandler("getchannels", get_channels))
    application.add_handler(CallbackQueryHandler(task_action))
    await application.initialize()
    await application.start()
    print("[+] Bot started")
    await application.updater.start_polling()

async def main():
    if not client.is_connected():
        print("[!] Client not connected. Connecting now...")
        await client.connect()

    print("[+] Telethon client started")
    await asyncio.gather(
        start_bot(),
        forward_messages()
    )
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
