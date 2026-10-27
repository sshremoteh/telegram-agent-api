"""
MCP Server for Local Telegram Agent API.
Communicates via stdio transport and proxies tool calls to the loopback REST API.
"""
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import httpx
from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

API_HOST = os.getenv("API_HOST", "127.0.0.1").strip()
API_PORT = int(os.getenv("API_PORT", "8765"))
API_TOKEN = os.getenv("API_TOKEN", "").strip()
BASE_URL = f"http://{API_HOST}:{API_PORT}"

mcp = FastMCP("telegram-agent")

async def _request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0
) -> Any:
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
        try:
            resp = await client.request(
                method=method,
                url=f"{BASE_URL}{path}",
                headers=headers,
                params=params,
                json=json_data
            )
            if resp.status_code == 401:
                return {"error": "Unauthorized: API_TOKEN is invalid or missing in .env"}
            if resp.status_code == 429:
                return {"error": f"Telegram FloodWait: {resp.text}"}
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            return {
                "error": f"Could not connect to Telegram Agent REST API at {BASE_URL}. Ensure server.py is running."
            }
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except Exception as e:
            return {"error": f"Request failed: {type(e).__name__}"}

@mcp.tool()
async def telegram_health() -> Dict[str, Any]:
    """Check the health status of the Local Telegram Agent API and its connection to Telegram."""
    return await _request("GET", "/health", timeout=10.0)

@mcp.tool()
async def telegram_me() -> Dict[str, Any]:
    """Get information about the authenticated Telegram user account (ID, name, username)."""
    return await _request("GET", "/me", timeout=15.0)

@mcp.tool()
async def telegram_dialogs(limit: int = 30) -> Dict[str, Any]:
    """List recent Telegram dialogs/conversations (chats, groups, channels).
    
    Args:
        limit: Number of dialogs to retrieve (1 to 100, default: 30).
    """
    if limit < 1 or limit > 100:
        return {"error": "limit must be between 1 and 100"}
    return await _request("GET", "/dialogs", params={"limit": limit}, timeout=30.0)

@mcp.tool()
async def telegram_history(chat: str, limit: int = 20) -> Dict[str, Any]:
    """Get recent message history from a specific Telegram chat.
    
    Args:
        chat: Target chat identifier (username, phone number, or chat ID).
        limit: Number of messages to retrieve (1 to 100, default: 20).
    """
    if not chat or not chat.strip():
        return {"error": "chat cannot be empty"}
    if limit < 1 or limit > 100:
        return {"error": "limit must be between 1 and 100"}
    return await _request("GET", "/history", params={"chat": chat.strip(), "limit": limit}, timeout=30.0)

@mcp.tool()
async def telegram_send(chat: str, text: str) -> Dict[str, Any]:
    """Send a text message to a specific Telegram chat.
    
    Args:
        chat: Target chat identifier (username, phone number, or chat ID).
        text: Message content to send (up to 4096 characters).
    """
    if not chat or not chat.strip():
        return {"error": "chat cannot be empty"}
    if not text or not text.strip():
        return {"error": "text cannot be empty"}
    if len(text) > 4096:
        return {"error": "text exceeds maximum length of 4096 characters"}
    return await _request("POST", "/send", json_data={"chat": chat.strip(), "text": text}, timeout=30.0)

@mcp.tool()
async def telegram_wait_reply(chat: str, after_message_id: int = 0, timeout_seconds: int = 20) -> Dict[str, Any]:
    """Wait for a new message to arrive in a chat after a given message ID.
    Useful for testing bot replies or waiting for user responses. Note that agents should
    verify sender_id, message text, and correlation with prior commands.
    
    Args:
        chat: Target chat identifier (username, phone number, or chat ID).
        after_message_id: The ID of the last known message. Waits for messages with ID > after_message_id.
        timeout_seconds: Maximum time to wait in seconds (1 to 60, default: 20).
    """
    if not chat or not chat.strip():
        return {"error": "chat cannot be empty"}
    if after_message_id < 0:
        return {"error": "after_message_id must be non-negative"}
    if timeout_seconds < 1 or timeout_seconds > 60:
        return {"error": "timeout_seconds must be between 1 and 60"}
    
    return await _request(
        "POST",
        "/wait",
        json_data={
            "chat": chat.strip(),
            "after_message_id": after_message_id,
            "timeout_seconds": timeout_seconds
        },
        timeout=float(timeout_seconds + 10)
    )

@mcp.tool()
async def telegram_click_button(chat: str, message_id: int, button_index: int) -> Dict[str, Any]:
    """Click an inline keyboard button on a Telegram message by its index (0-based, left-to-right, top-to-bottom).
    
    Args:
        chat: Target chat identifier (username, phone number, or chat ID).
        message_id: Message ID containing the inline keyboard.
        button_index: 0-based index of the button to click.
    """
    if not chat or not chat.strip():
        return {"error": "chat cannot be empty"}
    if message_id < 1:
        return {"error": "message_id must be positive"}
    if button_index < 0:
        return {"error": "button_index must be non-negative"}
        
    return await _request(
        "POST",
        "/click",
        json_data={
            "chat": chat.strip(),
            "message_id": message_id,
            "button_index": button_index
        },
        timeout=30.0
    )

@mcp.tool()
async def telegram_search(chat: str, query: str, limit: int = 20) -> Dict[str, Any]:
    """Search for messages containing specific text within a single Telegram chat.
    
    Args:
        chat: Target chat identifier (username, phone number, or chat ID).
        query: Search query text.
        limit: Maximum number of messages to return (1 to 100, default: 20).
    """
    if not chat or not chat.strip():
        return {"error": "chat cannot be empty"}
    if not query or not query.strip():
        return {"error": "query cannot be empty"}
    if limit < 1 or limit > 100:
        return {"error": "limit must be between 1 and 100"}
        
    return await _request(
        "GET",
        "/search",
        params={
            "chat": chat.strip(),
            "q": query.strip(),
            "limit": limit
        },
        timeout=30.0
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
