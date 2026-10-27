"""
Local Telegram Agent REST API Server.
Exposes secure loopback-only REST endpoints for Telegram interaction.
"""
import asyncio
import ipaddress
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from telethon import TelegramClient, errors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("telegram_agent_api")

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

# Load and validate host
API_HOST = os.getenv("API_HOST", "127.0.0.1").strip()
API_PORT = int(os.getenv("API_PORT", "8765"))
API_TOKEN = os.getenv("API_TOKEN", "").strip()

def is_loopback(host: str) -> bool:
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        return False

if not is_loopback(API_HOST):
    raise ValueError(
        f"API_HOST '{API_HOST}' is not allowed. Only loopback interfaces (e.g. 127.0.0.1) are permitted."
    )

if not API_TOKEN:
    logger.warning("API_TOKEN is empty in .env. Requests will be rejected until configured.")

TELEGRAM_API_ID_STR = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_ID = int(TELEGRAM_API_ID_STR) if TELEGRAM_API_ID_STR.isdigit() else None
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "./data/telegram").strip()

session_p = Path(TELEGRAM_SESSION)
if not session_p.is_absolute():
    RESOLVED_SESSION = str((BASE_DIR / session_p).resolve())
else:
    RESOLVED_SESSION = str(session_p.resolve())

# State management
telegram_lock = asyncio.Lock()
telegram_client: Optional[TelegramClient] = None

# Security dependency
bearer_scheme = HTTPBearer(auto_error=False)

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)) -> str:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not API_TOKEN or not secrets.compare_digest(credentials.credentials, API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

# Helper functions
def parse_chat_target(chat: str) -> Any:
    chat_clean = chat.strip()
    try:
        return int(chat_clean)
    except ValueError:
        return chat_clean

def serialize_message(msg: Any) -> Dict[str, Any]:
    buttons = []
    if getattr(msg, "buttons", None):
        idx = 0
        for row in msg.buttons:
            row_btns = []
            for btn in row:
                row_btns.append({
                    "text": getattr(btn, "text", ""),
                    "index": idx
                })
                idx += 1
            buttons.append(row_btns)

    return {
        "id": getattr(msg, "id", None),
        "date": msg.date.isoformat() if getattr(msg, "date", None) else None,
        "sender_id": getattr(msg, "sender_id", None),
        "text": getattr(msg, "text", "") or getattr(msg, "message", "") or "",
        "out": bool(getattr(msg, "out", False)),
        "reply_to_msg_id": msg.reply_to.reply_to_msg_id if getattr(msg, "reply_to", None) else None,
        "buttons": buttons
    }

# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_client
    logger.info("Initializing Telegram Agent API...")
    
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.error("TELEGRAM_API_ID or TELEGRAM_API_HASH missing in .env")
        raise RuntimeError(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured in .env before starting the server."
        )

    session_file = Path(f"{RESOLVED_SESSION}.session")
    if not session_file.exists():
        logger.error(f"Session file not found at {session_file}. Run: python auth.py")
        raise RuntimeError(
            f"Session file '{session_file}' does not exist. Please authorize first by running: python auth.py"
        )

    client = TelegramClient(RESOLVED_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        logger.error("Telegram session is not authorized. Run: python auth.py")
        raise RuntimeError(
            "Telegram session is not authorized. Please run: python auth.py"
        )

    telegram_client = client
    logger.info("Telegram client connected and authorized successfully.")
    try:
        yield
    finally:
        if telegram_client:
            await telegram_client.disconnect()
            logger.info("Telegram client disconnected.")

# FastAPI app
app = FastAPI(
    title="Local Telegram Agent API",
    description="Secure loopback-only REST API for Telegram agent interactions.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# Exception handlers
@app.exception_handler(errors.FloodWaitError)
async def flood_wait_handler(request, exc: errors.FloodWaitError):
    logger.warning("Telegram FloodWaitError: %s seconds", exc.seconds)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Telegram flood wait: retry after {exc.seconds} seconds", "retry_after": exc.seconds},
        headers={"Retry-After": str(exc.seconds)},
    )

# Pydantic schemas
class SendMessageRequest(BaseModel):
    chat: str = Field(..., min_length=1, max_length=256, description="Username, chat ID or phone")
    text: str = Field(..., min_length=1, max_length=4096, description="Message text")

class WaitMessageRequest(BaseModel):
    chat: str = Field(..., min_length=1, max_length=256, description="Chat username or ID")
    after_message_id: int = Field(0, ge=0, description="Wait for messages with ID greater than this")
    timeout_seconds: int = Field(20, ge=1, le=60, description="Wait timeout in seconds")

class ClickButtonRequest(BaseModel):
    chat: str = Field(..., min_length=1, max_length=256, description="Chat username or ID")
    message_id: int = Field(..., ge=1, description="Message ID containing inline keyboard")
    button_index: int = Field(..., ge=0, description="0-based button index (left-to-right, top-to-bottom)")

# Endpoints
@app.get("/health", dependencies=[Depends(verify_token)])
async def get_health():
    is_connected = False
    is_authorized = False
    if telegram_client:
        is_connected = telegram_client.is_connected()
        try:
            is_authorized = await telegram_client.is_user_authorized()
        except Exception:
            is_authorized = False

    return {
        "status": "ok",
        "telegram_connected": is_connected,
        "is_authorized": is_authorized,
    }

@app.get("/me", dependencies=[Depends(verify_token)])
async def get_me():
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    try:
        async with telegram_lock:
            me = await telegram_client.get_me()
        if not me:
            raise HTTPException(status_code=404, detail="Account not found")
        return {
            "id": me.id,
            "first_name": me.first_name or "",
            "last_name": me.last_name or "",
            "username": me.username or "",
            "is_bot": bool(me.bot),
        }
    except errors.RPCError as e:
        logger.error("RPC error in get_me: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

@app.get("/dialogs", dependencies=[Depends(verify_token)])
async def get_dialogs(limit: int = Query(30, ge=1, le=100)):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    try:
        async with telegram_lock:
            dialogs = await telegram_client.get_dialogs(limit=limit)
        results = []
        for d in dialogs:
            results.append({
                "id": d.id,
                "title": d.title or d.name or "",
                "unread_count": d.unread_count,
                "is_user": d.is_user,
                "is_group": d.is_group,
                "is_channel": d.is_channel,
                "date": d.date.isoformat() if d.date else None,
            })
        return {"dialogs": results}
    except errors.RPCError as e:
        logger.error("RPC error in get_dialogs: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

@app.get("/history", dependencies=[Depends(verify_token)])
async def get_history(
    chat: str = Query(..., min_length=1, max_length=256),
    limit: int = Query(20, ge=1, le=100)
):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    target = parse_chat_target(chat)
    try:
        async with telegram_lock:
            entity = await telegram_client.get_entity(target)
            messages = await telegram_client.get_messages(entity, limit=limit)
        return {
            "chat": chat,
            "messages": [serialize_message(m) for m in messages]
        }
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat}")
    except errors.RPCError as e:
        logger.error("RPC error in get_history: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

@app.post("/send", dependencies=[Depends(verify_token)])
async def send_message(req: SendMessageRequest):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    target = parse_chat_target(req.chat)
    try:
        async with telegram_lock:
            entity = await telegram_client.get_entity(target)
            sent = await telegram_client.send_message(entity, req.text)
        return {
            "status": "sent",
            "id": sent.id,
            "date": sent.date.isoformat() if sent.date else None,
            "chat_id": getattr(entity, "id", None),
            "text": sent.text,
        }
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        raise HTTPException(status_code=404, detail=f"Chat not found: {req.chat}")
    except errors.RPCError as e:
        logger.error("RPC error in send_message: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

@app.post("/wait", dependencies=[Depends(verify_token)])
async def wait_reply(req: WaitMessageRequest):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    target = parse_chat_target(req.chat)
    try:
        async with telegram_lock:
            entity = await telegram_client.get_entity(target)
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        raise HTTPException(status_code=404, detail=f"Chat not found: {req.chat}")

    start_time = asyncio.get_event_loop().time()
    poll_interval = 1.0

    while True:
        try:
            # Lock is held only during the Telegram request, NOT during sleep!
            async with telegram_lock:
                messages = await telegram_client.get_messages(entity, limit=10)
        except errors.RPCError as e:
            logger.error("RPC error in wait poll: %s", type(e).__name__)
            raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

        new_messages = [m for m in messages if m.id > req.after_message_id]
        if new_messages:
            new_messages.sort(key=lambda m: m.id)
            found = new_messages[0]
            return {
                "status": "received",
                "message": serialize_message(found),
                "waited_seconds": round(asyncio.get_event_loop().time() - start_time, 2)
            }

        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= req.timeout_seconds:
            return {
                "status": "timeout",
                "message": None,
                "waited_seconds": round(elapsed, 2)
            }

        # Sleep without holding lock
        remaining = req.timeout_seconds - elapsed
        await asyncio.sleep(min(poll_interval, max(0.1, remaining)))

@app.post("/click", dependencies=[Depends(verify_token)])
async def click_button(req: ClickButtonRequest):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    target = parse_chat_target(req.chat)
    try:
        async with telegram_lock:
            entity = await telegram_client.get_entity(target)
            msg = await telegram_client.get_messages(entity, ids=req.message_id)
            if not msg:
                raise HTTPException(status_code=404, detail="Message not found")

            flat_buttons = []
            if getattr(msg, "buttons", None):
                for row in msg.buttons:
                    for btn in row:
                        flat_buttons.append(btn)

            if req.button_index >= len(flat_buttons):
                raise HTTPException(
                    status_code=400,
                    detail=f"Button index {req.button_index} out of range (message has {len(flat_buttons)} buttons)"
                )

            selected_btn = flat_buttons[req.button_index]
            btn_text = getattr(selected_btn, "text", "")
            await selected_btn.click()

        return {
            "status": "clicked",
            "message_id": req.message_id,
            "button_index": req.button_index,
            "button_text": btn_text
        }
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        raise HTTPException(status_code=404, detail=f"Chat not found: {req.chat}")
    except HTTPException:
        raise
    except errors.RPCError as e:
        logger.error("RPC error in click_button: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

@app.get("/search", dependencies=[Depends(verify_token)])
async def search_messages(
    chat: str = Query(..., min_length=1, max_length=256),
    q: str = Query(..., min_length=1, max_length=256),
    limit: int = Query(20, ge=1, le=100)
):
    if not telegram_client:
        raise HTTPException(status_code=503, detail="Telegram client not initialized")
    target = parse_chat_target(chat)
    try:
        async with telegram_lock:
            entity = await telegram_client.get_entity(target)
            messages = await telegram_client.get_messages(entity, search=q, limit=limit)
        return {
            "chat": chat,
            "query": q,
            "messages": [serialize_message(m) for m in messages]
        }
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat}")
    except errors.RPCError as e:
        logger.error("RPC error in search: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Telegram RPC error: {type(e).__name__}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=API_HOST, port=API_PORT, reload=False)
