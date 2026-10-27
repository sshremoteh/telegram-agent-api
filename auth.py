"""
Telegram Authentication Script.
Interactive authorization for Telethon MTProto client.
"""
import asyncio
import getpass
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, errors

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

def load_config() -> dict:
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
    
    api_id_str = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()
    session_path = os.getenv("TELEGRAM_SESSION", "./data/telegram").strip()
    
    api_id = int(api_id_str) if api_id_str.isdigit() else None
    
    p = Path(session_path)
    if not p.is_absolute():
        resolved_session = str((BASE_DIR / p).resolve())
    else:
        resolved_session = str(p.resolve())
        
    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "session_path": resolved_session,
    }

def ensure_secure_data_dir(session_path_str: str) -> None:
    session_dir = Path(session_path_str).parent
    session_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(session_dir, 0o700)
    except OSError:
        pass

def secure_session_files(session_path_str: str) -> None:
    session_file = Path(f"{session_path_str}.session")
    if session_file.exists():
        try:
            os.chmod(session_file, 0o600)
        except OSError:
            pass
    journal_file = Path(f"{session_path_str}.session-journal")
    if journal_file.exists():
        try:
            os.chmod(journal_file, 0o600)
        except OSError:
            pass

async def run_auth() -> int:
    config = load_config()
    api_id = config["api_id"]
    api_hash = config["api_hash"]
    phone = config["phone"]
    session_path = config["session_path"]
    
    if not api_id or not api_hash:
        print("\n" + "=" * 60)
        print("ОШИБКА: TELEGRAM_API_ID и/или TELEGRAM_API_HASH не настроены в .env")
        print("=" * 60)
        print("Инструкция по получению:")
        print("1. Перейдите в браузере на https://my.telegram.org")
        print("2. Войдите с вашим номером телефона Telegram.")
        print("3. Откройте раздел 'API development tools'.")
        print("4. Создайте приложение (App title и short name можно указать любые, например 'teleagent').")
        print("5. Скопируйте 'App api_id' и 'App api_hash'.")
        print(f"6. Откройте локальный файл {ENV_PATH} и укажите значения:")
        print("     TELEGRAM_API_ID=1234567")
        print("     TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef")
        print("     TELEGRAM_PHONE=+79991234567")
        print("7. Сохраните файл и запустите: python auth.py")
        print("=" * 60 + "\n")
        return 1

    ensure_secure_data_dir(session_path)

    print("Инициализация клиента Telegram...")
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            username = f"@{me.username}" if me.username else "без username"
            print("\n" + "=" * 60)
            print("Сессия уже авторизована!")
            print(f"Пользователь: {name} (ID: {me.id}, {username})")
            print(f"Файл сессии: {session_path}.session")
            print("=" * 60)
            secure_session_files(session_path)
            return 0

        # Not authorized yet
        if not phone:
            phone = input("Введите номер телефона в международном формате (+XXXXXXXXXXX): ").strip()
            if not phone:
                print("Ошибка: номер телефона не указан.")
                return 1

        print(f"Отправка запроса на авторизацию для {phone}...")
        await client.send_code_request(phone)

        code = input("Введите код подтверждения из Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except errors.SessionPasswordNeededError:
            print("Требуется пароль двухфакторной аутентификации (2FA).")
            pwd = getpass.getpass("Введите 2FA пароль: ")
            await client.sign_in(password=pwd)

        if await client.is_user_authorized():
            me = await client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            username = f"@{me.username}" if me.username else "без username"
            print("\n" + "=" * 60)
            print("Авторизация успешно завершена!")
            print(f"Аккаунт: {name} (ID: {me.id}, {username})")
            print(f"Файл сессии сохранён: {session_path}.session")
            print("=" * 60)
            secure_session_files(session_path)
            return 0
        else:
            print("Ошибка: авторизация не была завершена.")
            return 1
    except Exception as e:
        err_type = type(e).__name__
        print(f"Ошибка в процессе авторизации ({err_type}): {e}")
        return 1
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_auth())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nАвторизация прервана пользователем.")
        sys.exit(130)
