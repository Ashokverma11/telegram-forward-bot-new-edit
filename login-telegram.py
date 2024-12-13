from telethon import TelegramClient, events
import asyncio
from telethon.errors import SessionPasswordNeededError

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

if __name__ == "__main__":
    API_ID = '25324203'
    API_HASH = 'ea9b04db173a65635a7a483e20a2f123'
    BOT_TOKEN = '7595469262:AAE7oOPJu7DZieCdDE0vyc9_ADX7K8kTAnw'
    ALLOWED_USERNAME = 'itz36BoDa'
    client = TelegramClient('user_session', API_ID, API_HASH)
    asyncio.run(main())
