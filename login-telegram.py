from telethon import TelegramClient, events
import asyncio , time
from telethon.errors import SessionPasswordNeededError
import os
from dotenv import load_dotenv
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERNAME = os.getenv("ALLOWED_USERNAME")

async def login_user(phone, code=None, password=None):
    try:
        if not client.is_connected():
            await client.connect()

        if code is None:
            await client.send_code_request(phone)
            print(f"Code sent to {phone}.")
            return "awaiting_code"

        if password is None:
            await client.sign_in(phone=phone, code=code)
            print("Authenticated successfully!")
            return "authenticated"

        await client.sign_in(password=password)
        print("Logged in with 2FA!")
        return "authenticated"
    except SessionPasswordNeededError:
        print("2FA required. Please enter your password.")
        return "awaiting_password"
    except Exception as e:
        if "CODE_INVALID" in str(e):
            print("Invalid code. Please request a new code.")
        elif "PHONE_NUMBER_BANNED" in str(e):
            print("This phone number is banned by Telegram.")
        else:
            print(f"Unexpected error: {e}")
        return "error"
    
async def main():
    phone = input("Enter your phone number: ")
    status = await login_user(phone)

    if status == "awaiting_code":
        code = input("Enter the verification code: ")
        status = await login_user(phone, code=code)

    if status == "awaiting_password":
        password = input("Enter your 2FA password: ")
        status = await login_user(phone, code=code, password=password)

    if status == "authenticated":
        print("Login successful!")
    else:
        print("Login failed. Please try again.")
    print('Well Close After 10sec')
    time.sleep(10)
if __name__ == "__main__":
    client = TelegramClient('user_session', API_ID, API_HASH)
    asyncio.run(main())
