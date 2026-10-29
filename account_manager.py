"""
Multi-Account Manager for Telegram Agent API.
Manages account registry, session paths, and credential fallbacks.
"""
import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from telethon import TelegramClient

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
REGISTRY_PATH = DATA_DIR / "accounts.json"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

DEFAULT_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
DEFAULT_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
        os.chmod(SESSIONS_DIR, 0o700)
    except OSError:
        pass

def load_registry() -> Dict[str, Any]:
    ensure_dirs()
    if not REGISTRY_PATH.exists():
        # Check if legacy telegram.session exists and auto-migrate
        legacy_session = DATA_DIR / "telegram.session"
        initial_accounts = {}
        if legacy_session.exists():
            dest = SESSIONS_DIR / "default.session"
            if not dest.exists():
                shutil.copy2(legacy_session, dest)
            initial_accounts["default"] = {
                "alias": "default",
                "phone": os.getenv("TELEGRAM_PHONE", "").strip(),
                "api_id": int(DEFAULT_API_ID) if DEFAULT_API_ID.isdigit() else None,
                "api_hash": DEFAULT_API_HASH,
                "session_name": "default",
                "user_id": 7561104165,
                "first_name": "︂",
                "username": "SKAMEP_YMEP",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_active": True
            }
        data = {"active_account": "default" if "default" in initial_accounts else None, "accounts": initial_accounts}
        save_registry(data)
        return data
    
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active_account": None, "accounts": {}}

def save_registry(data: Dict[str, Any]):
    ensure_dirs()
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(REGISTRY_PATH, 0o600)
    except OSError:
        pass

def get_session_path(session_name: str) -> str:
    ensure_dirs()
    p = SESSIONS_DIR / session_name
    return str(p.resolve())

def get_account(alias: Optional[str] = None) -> Optional[Dict[str, Any]]:
    registry = load_registry()
    if not alias:
        alias = registry.get("active_account")
    if not alias:
        accounts = registry.get("accounts", {})
        if accounts:
            alias = next(iter(accounts.keys()))
    if not alias:
        return None
    return registry.get("accounts", {}).get(alias)

def get_active_account_name() -> Optional[str]:
    registry = load_registry()
    return registry.get("active_account")

def set_active_account(alias: str) -> bool:
    registry = load_registry()
    if alias not in registry.get("accounts", {}):
        return False
    registry["active_account"] = alias
    for name, acc in registry["accounts"].items():
        acc["is_active"] = (name == alias)
    save_registry(registry)
    return True

def list_accounts() -> List[Dict[str, Any]]:
    registry = load_registry()
    active = registry.get("active_account")
    result = []
    for alias, acc in registry.get("accounts", {}).items():
        item = dict(acc)
        item["is_active"] = (alias == active)
        # Check session file existence
        session_file = Path(f"{get_session_path(acc['session_name'])}.session")
        item["has_session_file"] = session_file.exists()
        result.append(item)
    return result

def register_account(
    alias: str,
    user_id: int,
    first_name: str,
    username: Optional[str] = None,
    phone: Optional[str] = None,
    api_id: Optional[int] = None,
    api_hash: Optional[str] = None,
) -> Dict[str, Any]:
    registry = load_registry()
    is_first = len(registry.get("accounts", {})) == 0
    acc_data = {
        "alias": alias,
        "phone": phone or "",
        "api_id": api_id or (int(DEFAULT_API_ID) if DEFAULT_API_ID.isdigit() else None),
        "api_hash": api_hash or DEFAULT_API_HASH,
        "session_name": alias,
        "user_id": user_id,
        "first_name": first_name or "",
        "username": username or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": is_first or (registry.get("active_account") == alias)
    }
    registry["accounts"][alias] = acc_data
    if is_first or not registry.get("active_account"):
        registry["active_account"] = alias
    save_registry(registry)
    return acc_data

def remove_account(alias: str) -> bool:
    registry = load_registry()
    if alias not in registry.get("accounts", {}):
        return False
    acc = registry["accounts"].pop(alias)
    session_file = Path(f"{get_session_path(acc['session_name'])}.session")
    if session_file.exists():
        try:
            session_file.unlink()
        except OSError:
            pass
    journal_file = Path(f"{get_session_path(acc['session_name'])}.session-journal")
    if journal_file.exists():
        try:
            journal_file.unlink()
        except OSError:
            pass
    if registry.get("active_account") == alias:
        remaining = list(registry.get("accounts", {}).keys())
        registry["active_account"] = remaining[0] if remaining else None
        if registry["active_account"]:
            registry["accounts"][registry["active_account"]]["is_active"] = True
    save_registry(registry)
    return True
