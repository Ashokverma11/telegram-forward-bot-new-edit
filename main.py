import sqlite3
import os
import asyncio
from telethon import TelegramClient, events
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, filters, MessageHandler
from dotenv import load_dotenv
from telethon.errors import SessionPasswordNeededError

load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")


class BotManager:
    def __init__(self, api_id, api_hash, bot_token):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.registered_handlers = {}  
        self.clients = {}  
        self.active_tasks = {} 
        self.init_db()
        self.load_all_tasks()

    def init_db(self):
        """Initializes the database for user tasks"""
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER,
                            name TEXT,
                            source_id INTEGER,
                            destination_id INTEGER,
                            enabled INTEGER DEFAULT 1,
                            edit_enabled INTEGER DEFAULT 1
                        )''')
        conn.commit()
        conn.close()

    def load_all_tasks(self):
        """Load all users and their tasks from the database"""
        self.active_tasks.clear()
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        cursor.execute('SELECT DISTINCT user_id FROM tasks')
        users = cursor.fetchall()

        for user in users:
            user_chat_id = user[0]
            self.active_tasks[user_chat_id] = {}

            cursor.execute('SELECT * FROM tasks WHERE user_id = ?', (user_chat_id,))
            tasks = cursor.fetchall()

            for task in tasks:
                task_id, _, name, source_id, destination_id, enabled, edit_enabled = task
                self.active_tasks[user_chat_id][task_id] = {
                    "source_id": source_id,
                    "destination_id": destination_id,
                    "enabled": bool(enabled),
                    "edit_enabled": bool(edit_enabled)
                }
                print(f"[DEBUG] Loaded Task: {task_id} | edit_enabled: {edit_enabled}")

        conn.close()
        print(f"[DEBUG] All active tasks: {self.active_tasks}")

    def get_or_create_client(self, user_chat_id):
        """Create or fetch a TelegramClient for the user"""
        if user_chat_id not in self.clients:
            session_file = f"user_session_{user_chat_id}.session"
            self.clients[user_chat_id] = TelegramClient(session_file, self.api_id, self.api_hash)
        return self.clients[user_chat_id]

    def add_task(self, user_chat_id, name, source_id, destination_id):
        """Add a forwarding task to the database and active tasks"""
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (user_id, name, source_id, destination_id, enabled, edit_enabled) VALUES (?, ?, ?, ?, ?, ?)',
                    (user_chat_id, name, source_id, destination_id, 1, 1))  
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        if user_chat_id not in self.active_tasks:
            self.active_tasks[user_chat_id] = {}
        self.active_tasks[user_chat_id][task_id] = {
            "source_id": source_id,
            "destination_id": destination_id,
            "enabled": True,
            "edit_enabled": True 
        }

    def get_user_tasks(self, user_chat_id):
        """Fetch all tasks for a specific user from the database"""
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE user_id = ?', (user_chat_id,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks

    def update_task(self, task_id, enabled=None, edit_enabled=None):
        """Update a specific task's properties"""
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        if enabled is not None:
            cursor.execute('UPDATE tasks SET enabled = ? WHERE id = ?', (enabled, task_id))
        if edit_enabled is not None:
            cursor.execute('UPDATE tasks SET edit_enabled = ? WHERE id = ?', (edit_enabled, task_id))

        conn.commit()
        conn.close()

        self.load_all_tasks()
        print(f"[DEBUG] Task {task_id} updated: enabled={enabled}, edit_enabled={edit_enabled}")

    def delete_task(self, task_id):
        """Disable and delete a task from the database and active tasks"""
        self.update_task(task_id, enabled=0)

        for user_chat_id, tasks in self.active_tasks.items():
            if task_id in tasks:
                client = self.get_or_create_client(user_chat_id)
                if task_id in self.registered_handlers:
                    print(f"[-] Removing handlers for Task {task_id}")
                    if "new_message_handler" in self.registered_handlers[task_id]:
                        client.remove_event_handler(self.registered_handlers[task_id]["new_message_handler"])
                    if "edit_message_handler" in self.registered_handlers[task_id]:
                        client.remove_event_handler(self.registered_handlers[task_id]["edit_message_handler"])
                    del self.registered_handlers[task_id]
                
                del self.active_tasks[user_chat_id][task_id]
                print(f"[-] Task {task_id} removed from active_tasks.")

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

        print(f"[+] Task {task_id} deleted from database.")


class ForwardBot:
    def __init__(self, bot_manager: BotManager):
        self.bot_manager = bot_manager
        self.awaiting_code = {}  
        self.awaiting_password = {} 

    @staticmethod
    def requires_connection(func):
        async def wrapper(self, update, context, *args, **kwargs):
            user_chat_id = update.effective_chat.id
            client = self.bot_manager.get_or_create_client(user_chat_id) 
            
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    await update.message.reply_text("❌ You are not connected. Please use `/connect` to log in.")
                    return
            except Exception as e:
                await update.message.reply_text(f"❌ Connection error: {e}")
                return
            
            return await func(self, update, context, *args, **kwargs)
        return wrapper

    async def start(self, update: Update, context: CallbackContext):
        """Start command for the bot"""
        user_chat_id = update.effective_chat.id
        await update.message.reply_text(f"Welcome to the Forward Bot!\nYour Chat ID: {user_chat_id}")


    async def connect_number(self, update: Update, context: CallbackContext):
        """Handle user connection and send verification code"""
        user_chat_id = update.effective_chat.id
        if context.args:
            phone_number = context.args[0]
            client = self.bot_manager.get_or_create_client(user_chat_id)

            try:
                await client.connect() 
                await client.send_code_request(phone=phone_number)
                self.awaiting_code[user_chat_id] = {
                    "phone": phone_number,
                    "awaiting": True
                }
                await update.message.reply_text(
                    "Code sent! Please enter the verification code:\n\nFor example, if your code is 123456, then enter it as `mycode123456` with no spaces."
                )
            except Exception as e:
                print(f"[!] Error sending code to {phone_number}: {e}")
                await update.message.reply_text(f"Error sending code: {e}")
        else:
            await update.message.reply_text("Please provide your phone number like this: `/connect <phonenumber>`")

    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages for phone verification"""
        user_chat_id = update.effective_chat.id
        text = update.message.text.strip()
        client = self.bot_manager.get_or_create_client(user_chat_id)

        if user_chat_id in self.awaiting_code and self.awaiting_code[user_chat_id]["awaiting"]:
            code = text.replace("mycode", "").strip()
            phone_number = self.awaiting_code[user_chat_id]["phone"]
            try:
                await client.sign_in(phone=phone_number, code=code)
                self.awaiting_code[user_chat_id]["awaiting"] = False
                await update.message.reply_text("You have been successfully authenticated!")
                print(f"[+] Successfully authenticated -> {phone_number}")
            except SessionPasswordNeededError:
                self.awaiting_code[user_chat_id]["awaiting"] = False
                self.awaiting_password[user_chat_id] = {"phone": phone_number, "awaiting": True}
                await update.message.reply_text("This account is protected by a 2FA password. Please enter your password:")
            except Exception as e:
                print(f"[!] Error during sign-in with code for {phone_number}: {e}")
                await update.message.reply_text(f"Error during sign-in: {e}")

        elif user_chat_id in self.awaiting_password and self.awaiting_password[user_chat_id]["awaiting"]:
            password = text
            phone_number = self.awaiting_password[user_chat_id]["phone"]
            try:
                await client.sign_in(password=password)
                self.awaiting_password[user_chat_id]["awaiting"] = False
                await update.message.reply_text("You have been successfully authenticated with 2FA!")
                print(f"[+] Successfully authenticated with 2FA -> {phone_number}")
            except Exception as e:
                print(f"[!] Error during 2FA authentication for {phone_number}: {e}")
                await update.message.reply_text(f"Error during 2FA authentication: {e}")
   
    @requires_connection
    async def add_forward(self, update: Update, context: CallbackContext):
        """Add a forwarding task for a user"""
        user_chat_id = update.effective_chat.id
        args = context.args 
        if len(args) == 5 and args[3] == "->":
            try:
                name = args[1]
                source_id = int(args[2])
                destination_id = int(args[4])
                self.bot_manager.add_task(user_chat_id, name, source_id, destination_id)
                await update.message.reply_text(f"Forward task '{name}' added successfully!")
            except ValueError:
                await update.message.reply_text("Invalid input! Use numeric IDs for source and destination.")
        else:
            await update.message.reply_text("Usage: /forward add NameLabel source_id -> destination_id")

    @requires_connection
    async def manage_tasks(self, update: Update, context: CallbackContext):
        """Manage tasks for a user"""
        user_chat_id = update.effective_chat.id
        tasks = self.bot_manager.get_user_tasks(user_chat_id)
        keyboard = []
        
        for task in tasks:
            task_id, _, name, source_id, destination_id, enabled, edit_enabled = task
            status = "Enabled" if enabled else "Disabled"
            
            keyboard.append([
                InlineKeyboardButton(f"{name} ({status})", callback_data=f"manage_{task_id}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Manage Forwarding Tasks:", reply_markup=reply_markup)

    async def task_action(self, update: Update, context: CallbackContext):
        """Handle task actions from inline buttons"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_chat_id = query.message.chat.id

        # print(f"[DEBUG] Callback data received: {data}")

        if "_" not in data:
            print(f"[!] Invalid callback data format: {data}")
            await query.edit_message_text("Invalid action format. Please try again.")
            return

        action, task_id_str = data.rsplit("_", 1)

        if not task_id_str.isdigit():
            print(f"[!] Task ID is not an integer: {task_id_str}")
            await query.edit_message_text("Invalid task ID. Please try again.")
            return

        task_id = int(task_id_str)

        if action == "manage":
            tasks = {task[0]: task for task in self.bot_manager.get_user_tasks(user_chat_id)}
            task = tasks.get(task_id)

            if task:
                name, _, _, _, enabled, edit_enabled = task[:6]
                status = "Enabled" if enabled else "Disabled"
                edit_status = "Edit: Enabled" if edit_enabled else "Edit: Disabled"

                keyboard = [
                    [InlineKeyboardButton("Enable", callback_data=f"enable_{task_id}"),
                    InlineKeyboardButton("Disable", callback_data=f"disable_{task_id}")],
                    [InlineKeyboardButton("Delete", callback_data=f"delete_{task_id}")],
                    [InlineKeyboardButton(edit_status, callback_data=f"toggle_edit_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"Task Actions for '{name}':", reply_markup=reply_markup)

        elif action == "toggle_edit":
            tasks = {task[0]: task for task in self.bot_manager.get_user_tasks(user_chat_id)}
            task = tasks.get(task_id)

            if task:
                current_edit_status = task[6]  # Access `edit_enabled`
                new_edit_status = 0 if current_edit_status else 1
                self.bot_manager.update_task(task_id, edit_enabled=new_edit_status)

                edit_status = "Edit: Enabled" if new_edit_status else "Edit: Disabled"
                keyboard = [
                    [InlineKeyboardButton("Enable", callback_data=f"enable_{task_id}"),
                    InlineKeyboardButton("Disable", callback_data=f"disable_{task_id}")],
                    [InlineKeyboardButton("Delete", callback_data=f"delete_{task_id}")],
                    [InlineKeyboardButton(edit_status, callback_data=f"toggle_edit_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(f"Task Actions for '{task[2]}':", reply_markup=reply_markup)
            else:
                print(f"[!] Task ID {task_id} not found.")
                await query.edit_message_text("Task not found.")

        elif action in ["enable", "disable", "delete"]:
            if action == "enable":
                self.bot_manager.update_task(task_id, enabled=1)
                await query.edit_message_text(f"Task enabled.")
            elif action == "disable":
                self.bot_manager.update_task(task_id, enabled=0)
                await query.edit_message_text(f"Task disabled.")
            elif action == "delete":
                self.bot_manager.delete_task(task_id)
                await query.edit_message_text(f"Task deleted.")
            self.bot_manager.load_all_tasks()
        else:
            print(f"[!] Unknown action: {action}")
            await query.edit_message_text("Unknown action. Please try again.")

    async def check_connection(self, update: Update, context: CallbackContext):
        """Check the connection status of the client"""
        user_chat_id = update.effective_chat.id
        client = self.bot_manager.get_or_create_client(user_chat_id) 
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await update.message.reply_text("The client is not authorized. Please use `/connect` to log in.")
                return
        except Exception as e:
            print(f"[!] Error connecting client for user {user_chat_id}: {e}")
            await update.message.reply_text(f"Error connecting to Telegram: {e}")
            return

        try:
            account_info = await client.get_me()
            account_name = account_info.first_name
            account_username = account_info.username
            await update.message.reply_text(
                f"The client is connected!\nCurrent account details:\n"
                f"Name: {account_name}\nUsername: @{account_username if account_username else 'No username set'}"
            )
        except Exception as e:
            print(f"[!] Error fetching account details for user {user_chat_id}: {e}")
            await update.message.reply_text("The client is connected, but unable to fetch account details.")

    async def forward_messages(self):
        """Forward messages and handle edited messages for all active tasks"""
        self.locks = {}

        while True:
            for user_chat_id in list(self.bot_manager.active_tasks.keys()):
                client = self.bot_manager.get_or_create_client(user_chat_id)
                try:
                    await client.connect()
                    if not await client.is_user_authorized():
                        print(f"[-] Client for user {user_chat_id} is not authorized.")
                        del self.bot_manager.active_tasks[user_chat_id]
                        continue

                    for task_id, task_details in list(self.bot_manager.active_tasks[user_chat_id].items()):
                        async with self.locks.setdefault(task_id, asyncio.Lock()):
                            source_id = task_details["source_id"]
                            destination_id = task_details["destination_id"]
                            enabled = task_details["enabled"]
                            edit_enabled = task_details["edit_enabled"]

                            if not enabled:
                                # Remove handlers if the task is disabled
                                if task_id in self.bot_manager.registered_handlers:
                                    print(f"[-] Removing handlers for disabled Task {task_id}")
                                    client.remove_event_handler(self.bot_manager.registered_handlers[task_id]["new_message_handler"])
                                    if "edit_message_handler" in self.bot_manager.registered_handlers[task_id]:
                                        client.remove_event_handler(self.bot_manager.registered_handlers[task_id]["edit_message_handler"])
                                    del self.bot_manager.registered_handlers[task_id]
                                continue

                            if enabled and task_id not in self.bot_manager.registered_handlers:
                                @client.on(events.NewMessage(chats=source_id))
                                async def handle_new_message(event, dest=destination_id, t_id=task_id):
                                    async with self.locks.setdefault(t_id, asyncio.Lock()):
                                        try:
                                            await client.send_message(dest, event.message.text or event.message.message)
                                            print(f"[{user_chat_id}] Message forwarded from {source_id} to {destination_id}")
                                        except Exception as e:
                                            print(f"[{user_chat_id}] Error forwarding message: {e}")

                                @client.on(events.MessageEdited(chats=source_id))
                                async def handle_message_edit(event, dest=destination_id, t_id=task_id):
                                    if not edit_enabled:
                                        print(f"[{user_chat_id}] Edit ignored for Task ID {t_id}")
                                        return

                                    async with self.locks.setdefault(t_id, asyncio.Lock()):
                                        try:
                                            if event.message.text:
                                                await client.send_message(dest, event.message.text)
                                                print(f"[{user_chat_id}] Edited message forwarded to {destination_id}: {event.message.text}")
                                            elif event.message.media:
                                                await client.send_file(dest, event.message.media)
                                                print(f"[{user_chat_id}] Edited media forwarded to {destination_id}")
                                        except Exception as e:
                                            print(f"[{user_chat_id}] Error forwarding edited message: {e}")

                                self.bot_manager.registered_handlers[task_id] = {
                                    "new_message_handler": handle_new_message,
                                    "edit_message_handler": handle_message_edit
                                }
                                print(f"[+] Handlers added for Task ID {task_id}")

                except Exception as e:
                    print(f"[!] Error processing tasks for user {user_chat_id}: {e}")

            await asyncio.sleep(1)
    async def get_channels(self, update: Update, context: CallbackContext):
        """Fetch and display all channels for the current user's client"""
        user_chat_id = update.effective_chat.id
        client = self.bot_manager.get_or_create_client(user_chat_id)  

        try:
            await client.connect()
            if not await client.is_user_authorized():
                await update.message.reply_text("Your client is not authorized. Please use /connect to log in.")
                return

            dialogs = await client.get_dialogs()
            response = "📋 All Channels:\n\n"

            for dialog in dialogs:
                if dialog.is_channel:
                    try:
                        name = dialog.name or "Unnamed"
                        chat_id = dialog.entity.id
                        response += f"{name} -> {chat_id}\n"
                    except Exception as e:
                        print(f"Error fetching channel details: {e}")
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
            print(f"[!] Error fetching channels for user {user_chat_id}: {e}")
            await update.message.reply_text(f"Error fetching channels: {e}")

    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages for phone verification"""
        user_chat_id = update.effective_chat.id
        text = update.message.text.strip()
        client = self.bot_manager.get_or_create_client(user_chat_id)

        if user_chat_id in self.awaiting_code and self.awaiting_code[user_chat_id]["awaiting"]:
            code = text.replace("mycode", "").strip()
            phone_number = self.awaiting_code[user_chat_id]["phone"]
            try:
                await client.sign_in(phone=phone_number, code=code)
                self.awaiting_code[user_chat_id]["awaiting"] = False
                await update.message.reply_text("You have been successfully authenticated!")
                print(f"[+] Successfully authenticated -> {phone_number}")
            except SessionPasswordNeededError:
                self.awaiting_code[user_chat_id]["awaiting"] = False
                self.awaiting_password[user_chat_id] = {"phone": phone_number, "awaiting": True}
                await update.message.reply_text("This account is protected by a 2FA password. Please enter your password:")
            except Exception as e:
                print(f"[!] Error during sign-in with code for {phone_number}: {e}")
                await update.message.reply_text(f"Error during sign-in: {e}")

        elif user_chat_id in self.awaiting_password and self.awaiting_password[user_chat_id]["awaiting"]:
            password = text
            phone_number = self.awaiting_password[user_chat_id]["phone"]
            try:
                await client.sign_in(password=password)
                self.awaiting_password[user_chat_id]["awaiting"] = False
                await update.message.reply_text("You have been successfully authenticated with 2FA!")
                print(f"[+] Successfully authenticated with 2FA -> {phone_number}")
            except Exception as e:
                print(f"[!] Error during 2FA authentication for {phone_number}: {e}")
                await update.message.reply_text(f"Error during 2FA authentication: {e}")


    async def start_bot(self):
        """Start the bot"""
        application = Application.builder().token(self.bot_manager.bot_token).build()
        application.add_handler(CommandHandler("connect", self.connect_number))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("forward", self.add_forward))
        application.add_handler(CommandHandler("getchannels", self.get_channels))
        application.add_handler(CommandHandler("manage", self.manage_tasks))
        application.add_handler(CommandHandler("check_connection", self.check_connection))
        application.add_handler(CallbackQueryHandler(self.task_action))
        await application.initialize()
        await application.start()
        print('[+] Bot Starting')
        await application.updater.start_polling()

    async def main(self):
        """Main entry point for the bot"""
        await asyncio.gather(
            self.start_bot(),
            self.forward_messages()
        )
        await asyncio.Event().wait()

if __name__ == "__main__":
    bot_manager = BotManager(API_ID, API_HASH, BOT_TOKEN)
    forward_bot = ForwardBot(bot_manager)
    asyncio.run(forward_bot.main())
