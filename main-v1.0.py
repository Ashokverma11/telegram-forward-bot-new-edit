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
    
async def join_group(link):
    try:
        entity = await client.get_entity(link)
        if hasattr(entity, 'left') and not entity.left:
            print(f"Already a member of the group/channel: {entity.title or entity.id}")
            return entity
        
        if "joinchat" in link or "+" in link:
            invite_code = link.split('/')[-1].replace('+', '')
            result = await client(ImportChatInviteRequest(invite_code))
            print(f"Successfully joined the private group: {link}")
            return result
        else:
            await client(JoinChannelRequest(link))
            print(f"Successfully joined the public group or channel: {link}")
            return entity
    except Exception as e:
        try:
            await client(JoinChannelRequest(link))
            print(f"Successfully joined the public group or channel: {link}")
            return entity
        except:
            pass
        print(f"Error joining group or channel {link}: {e}")
        error_message = (
            f"⚠️ Error occurred while trying to join the group/channel:\n"
            f"Link: {link}\n"
            f"Error: {e}\n"
            f"Please join manually and delete the task if necessary."
        )
        try:
            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(chat_id=user_chat_id, text=error_message)
            print('[+] Success Send Message')
        except Exception as send_error:
            print(f"Failed to send error message to user chat: {send_error}")

        return None
    
async def join_channel_temporarily(channel):
    try:
        print(f"Joining channel: {channel}")
        await client(JoinChannelRequest(channel))
        print(f"Joined channel: {channel}")
        return await client.get_entity(channel)
    except Exception as e:
        if 'that you are not part of. Join the group and retry' in str(e):
            print(e,channel)
            return await join_group(channel)
        else:
            print(f"Error joining channel {channel}: {e}")
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

        # Remove handlers for deleted or disabled tasks
        for task_id in list(active_tasks.keys()):
            task = next((t for t in tasks if t[0] == task_id), None)
            if not task or not task[4]:  # Task doesn't exist or is disabled
                print(f"Removing event handler for Task ID: {task_id}")
                client.remove_event_handler(active_tasks[task_id]['handler'])
                del active_tasks[task_id]

        # Add handlers for new tasks or re-enabled tasks
        for task in tasks:
            task_id, name, source_id, destination_id, enabled, edit_enabled = task

            if enabled and task_id not in active_tasks:
                try:
                    source_entity = await join_group(source_id)
                    if not source_entity:
                        print(f"Source entity for Task ID {task_id} is None. Disabling task and notifying user.")
                        update_task(task_id, enabled=0)
                        error_message = (
                            f"⚠️ Task ID {task_id} has been disabled.\n"
                            f"Reason: Unable to join or access source group/channel with ID or URL: {source_id}."
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

async def check_and_listen_channel(channel_username):
    try:
        # Get the channel entity
        entity = await client.get_entity(channel_username)
        print(f"Resolved Entity: {entity.title} | ID: {entity.id}")

        messages = await client.get_messages(entity, limit=1)

        if messages:
            print("Found old messages. Leaving the channel...")
            await client(LeaveChannelRequest(entity))
        else:
            print("No old messages found. Joining the channel and leaving...")
            await join_group(f"https://t.me/{channel_username}")
            await client(LeaveChannelRequest(entity))

        print(f"Completed checking channel: {channel_username}")

    except Exception as e:
        print(f"Error checking or leaving channel: {e}")

async def start(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id
    await update.message.reply_text(f"Welcome to the Forward Bot! Use /help to see available commands...\nYour Chat ID: {user_chat_id}")

async def add_forward(update: Update, context: CallbackContext):
    global user_chat_id
    user_chat_id = update.effective_chat.id
    args = context.args
    if len(args) == 5 and args[3] == "->":
        name = args[1]
        source_id = args[2]
        destination_id = args[4]
        add_task(name, source_id, destination_id)
        await update.message.reply_text(f"Forward task '{name}' added!")
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
