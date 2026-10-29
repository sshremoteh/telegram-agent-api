"""
Script to clean up Telegram account:
- Deletes all dialogs (chats, groups, channels) except Saved Messages and Telegram Notifications (777000).
- Blocks all bots before deleting their dialogs.
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, errors
from telethon.tl.functions.contacts import BlockRequest

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

API_ID_STR = os.getenv("TELEGRAM_API_ID", "").strip()
API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
SESSION = os.getenv("TELEGRAM_SESSION", "./data/telegram").strip()

session_p = Path(SESSION)
if not session_p.is_absolute():
    RESOLVED_SESSION = str((BASE_DIR / session_p).resolve())
else:
    RESOLVED_SESSION = str(session_p.resolve())

async def main():
    if not API_ID_STR or not API_HASH:
        print("Error: API credentials missing in .env")
        return

    client = TelegramClient(
        RESOLVED_SESSION,
        int(API_ID_STR),
        API_HASH,
        device_model="Desktop",
        system_version="Linux",
        app_version="5.4.1",
        lang_code="ru",
        system_lang_code="ru"
    )
    await client.connect()

    if not await client.is_user_authorized():
        print("Error: Client not authorized.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID: {me.id}, @{me.username})")

    # Fetch all dialogs
    print("Fetching dialogs...")
    dialogs = await client.get_dialogs()
    print(f"Total dialogs found: {len(dialogs)}")

    deleted_count = 0
    blocked_count = 0
    skipped_count = 0

    for d in dialogs:
        # Never delete Saved Messages (self) or Telegram Service Notifications (777000)
        if d.id == me.id or d.id == 777000:
            print(f"[SKIP] Keeping essential dialog: {d.title or d.name} (ID: {d.id})")
            skipped_count += 1
            continue

        title = d.title or d.name or str(d.id)
        is_bot = bool(getattr(d.entity, "bot", False))

        try:
            # If entity is a bot, block it
            if is_bot:
                try:
                    await client(BlockRequest(id=d.input_entity))
                    print(f"[BLOCK] Blocked bot: {title} (ID: {d.id})")
                    blocked_count += 1
                except Exception as e:
                    print(f"[WARN] Failed to block bot {title}: {e}")

            # Delete dialog (leaves channels/groups or clears history with user)
            await client.delete_dialog(d.input_entity)
            print(f"[DELETE] Deleted dialog: {title} (ID: {d.id})")
            deleted_count += 1

            # Polite delay to prevent flood waits
            await asyncio.sleep(1.2)

        except errors.FloodWaitError as e:
            print(f"[FLOOD WAIT] Need to wait {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 2)
            try:
                await client.delete_dialog(d.input_entity)
                print(f"[DELETE after wait] Deleted dialog: {title} (ID: {d.id})")
                deleted_count += 1
            except Exception as retry_err:
                print(f"[ERROR] Retry failed for {title}: {retry_err}")
        except Exception as e:
            print(f"[ERROR] Could not process {title} (ID: {d.id}): {e}")

    print("\n" + "=" * 50)
    print("Cleanup completed successfully!")
    print(f"Dialogs deleted/left: {deleted_count}")
    print(f"Bots blocked: {blocked_count}")
    print(f"Preserved essential dialogs: {skipped_count}")
    print("=" * 50)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
