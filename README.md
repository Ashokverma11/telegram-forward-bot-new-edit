# Telegram Forward Bot

This repository contains the source code for a Telegram bot that facilitates message forwarding between channels and groups. The bot is built using Python, leveraging the `Telethon` and `python-telegram-bot` libraries for its functionality.

---

## Features

- **Forward Messages**: Automatically forward messages from one channel/group to another.
- **Edited Message Handling**: Forward edits to messages if configured.
- **Task Management**: Add, delete, enable, or disable tasks for forwarding messages.
- **User Connection**: Allows users to connect their Telegram account via phone number and manage their tasks.
- **Channel Listing**: Fetch and display a list of all channels associated with the user's Telegram account.

---

## Setup Instructions

### Prerequisites

1. Install Python 3.8 or higher.
2. Install required dependencies:
   ```bash
   pip install telethon python-telegram-bot python-dotenv
   ```
3. Set up a bot on Telegram using BotFather to obtain a bot token.

### Configuration

1. Create a `.env` file in the project root directory with the following:
   ```env
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   BOT_TOKEN=your_telegram_bot_token
   ```

2. Initialize the database:
   ```bash
   python -c "import sqlite3; sqlite3.connect('tasks.db').execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, source_id INTEGER, destination_id INTEGER, enabled INTEGER DEFAULT 1, edit_enabled INTEGER DEFAULT 1)')"
   ```

---

## Usage

### Starting the Bot
Run the bot using:
```bash
python main.py
```

### Bot Commands

- `/start`: Start the bot and display the welcome message.
- `/connect <phone_number>`: Connect your Telegram account using the specified phone number.
- `/forward add <NameLabel> <source_id> -> <destination_id>`: Add a forwarding task.
- `/getchannels`: List all channels/groups linked to the user’s account.
- `/manage`: Manage your forwarding tasks.
- `/check_connection`: Check the connection status of the client.

---

## Development Notes

- **Database**: The bot uses SQLite for managing tasks.
- **Asynchronous Design**: The bot uses asynchronous event handling for efficient performance.
- **Error Handling**: Includes basic error handling for common issues such as unauthorized sessions or incorrect input formats.

---

## Contributing

Feel free to fork this repository, submit issues, or create pull requests for enhancements or bug fixes.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
