"""
Telegram Authentication Script with Multi-Account Support.
Interactive authorization for Telethon MTProto client.
"""
import asyncio
import getpass
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, errors
import account_manager

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

def load_config() -> dict:
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
    
    api_id_str = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()
    
    api_id = int(api_id_str) if api_id_str.isdigit() else None
    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
    }

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

async def run_auth(alias: str = "default", phone_input: str = None) -> int:
    config = load_config()
    api_id = config["api_id"]
    api_hash = config["api_hash"]
    phone = phone_input or config["phone"]
    
    if not api_id or not api_hash:
        print("\n" + "=" * 60)
        print("ОШИБКА: TELEGRAM_API_ID и/или TELEGRAM_API_HASH не настроены в .env")
        print("=" * 60)
        print("Инструкция по получению:")
        print("1. Перейдите в браузере на https://my.telegram.org")
        print("2. Войдите с вашим номером телефона Telegram.")
        print("3. Откройте раздел 'API development tools'.")
        print("4. Создайте приложение.")
        print("5. Скопируйте 'App api_id' и 'App api_hash'.")
        print(f"6. Откройте локальный файл {ENV_PATH} и укажите значения:")
        print("     TELEGRAM_API_ID=1234567")
        print("     TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef")
        print("7. Сохраните файл и запустите: python auth.py")
        print("=" * 60 + "\n")
        return 1

    session_path = account_manager.get_session_path(alias)

    print(f"\n[+] Инициализация авторизации для аккаунта: '{alias}'...")
    client = TelegramClient(
        session_path,
        api_id,
        api_hash,
        device_model="Desktop",
        system_version="Linux",
        app_version="5.4.1",
        lang_code="ru",
        system_lang_code="ru"
    )
    await client.connect()

    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            username = f"@{me.username}" if me.username else "без username"
            print("\n" + "=" * 60)
            print(f"Сессия '{alias}' уже авторизована!")
            print(f"Пользователь: {name} (ID: {me.id}, {username})")
            print(f"Файл сессии: {session_path}.session")
            print("=" * 60)
            secure_session_files(session_path)
            account_manager.register_account(
                alias=alias,
                user_id=me.id,
                first_name=me.first_name or "",
                username=me.username,
                phone=phone,
                api_id=api_id,
                api_hash=api_hash
            )
            return 0

        if not phone:
            phone = input("Введите номер телефона в международном формате (+XXXXXXXXXXX): ").strip()
            if not phone:
                print("Ошибка: номер телефона не указан.")
                return 1

        print(f"Отправка запроса на авторизацию для {phone}...")
        sent_code = await client.send_code_request(phone)
        
        code_type = type(sent_code.type).__name__
        print("\n" + "-" * 50)
        if code_type == "SentCodeTypeApp":
            print(">> Код отправлен в приложение Telegram (в чат 'Telegram' со служебными уведомлениями).")
            print(">> Проверьте официальное приложение Telegram на смартфоне или ПК!")
        elif code_type == "SentCodeTypeSms":
            print(">> Код отправлен по СМС на номер телефона.")
        elif code_type == "SentCodeTypeEmailCode":
            pattern = getattr(sent_code.type, "email_pattern", "скрыт")
            print(f">> Код отправлен на привязанную электронную почту (Email: {pattern}).")
            print(">> Проверьте входящие и папку 'Спам' в вашей почте!")
        elif code_type == "SentCodeTypeCall":
            print(">> Ожидайте телефонный звонок (робот продиктует код).")
        elif code_type == "SentCodeTypeFragmentSms":
            print(">> Номер привязан к Fragment, проверьте платформу Fragment.")
        else:
            print(f">> Способ доставки кода: {code_type}")
        
        if getattr(sent_code, "timeout", None):
            print(f">> Время действия кода: {sent_code.timeout} сек.")
        print("-" * 50 + "\n")

        code = input("Введите код подтверждения из Telegram: ").strip()
        try:
            await client.sign_in(phone, code, phone_code_hash=sent_code.phone_code_hash)
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
            print(f"Аккаунт '{alias}': {name} (ID: {me.id}, {username})")
            print(f"Файл сессии сохранён: {session_path}.session")
            print("=" * 60)
            secure_session_files(session_path)
            account_manager.register_account(
                alias=alias,
                user_id=me.id,
                first_name=me.first_name or "",
                username=me.username,
                phone=phone,
                api_id=api_id,
                api_hash=api_hash
            )
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
    target_alias = "default"
    if len(sys.argv) > 1:
        target_alias = sys.argv[1].strip()
    else:
        accounts = account_manager.list_accounts()
        if accounts:
            print("Существующие аккаунты:")
            for a in accounts:
                mark = "*" if a["is_active"] else " "
                print(f" [{mark}] {a['alias']} (ID: {a['user_id']}, @{a['username']})")
            ans = input(f"\nВведите имя для нового или существующего аккаунта [по умолчанию: {accounts[0]['alias']}]: ").strip()
            if ans:
                target_alias = ans
            else:
                target_alias = accounts[0]['alias']
        else:
            ans = input("Введите имя первого аккаунта [default]: ").strip()
            if ans:
                target_alias = ans

    try:
        exit_code = asyncio.run(run_auth(alias=target_alias))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nАвторизация прервана пользователем.")
        sys.exit(130)
