"""
Unit tests for validation, models, security checks, and endpoints.
These tests run without any connection to Telegram or external networks.
"""
import os
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure test environment does not depend on live credentials
os.environ["API_HOST"] = "127.0.0.1"
os.environ["API_PORT"] = "8765"
if not os.environ.get("API_TOKEN"):
    os.environ["API_TOKEN"] = "test-token-safe-for-unit-tests"

from server import (
    app,
    is_loopback,
    parse_chat_target,
    serialize_message,
    SendMessageRequest,
    WaitMessageRequest,
    ClickButtonRequest,
    DeleteDialogRequest,
    BlockUserRequest,
    API_TOKEN,
)

def test_delete_and_block_request_validation():
    """Verify DeleteDialogRequest and BlockUserRequest models."""
    del_req = DeleteDialogRequest(chat="@testchat")
    assert del_req.chat == "@testchat"
    with pytest.raises(ValidationError):
        DeleteDialogRequest(chat="")

    block_req = BlockUserRequest(chat="123456")
    assert block_req.chat == "123456"
    with pytest.raises(ValidationError):
        BlockUserRequest(chat="")

def test_loopback_validation():
    """Verify that loopback detection correctly accepts localhost and rejects external IPs."""
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("localhost") is True
    assert is_loopback("127.0.0.2") is True
    assert is_loopback("::1") is True
    
    assert is_loopback("0.0.0.0") is False
    assert is_loopback("192.168.1.50") is False
    assert is_loopback("10.0.0.1") is False
    assert is_loopback("8.8.8.8") is False
    assert is_loopback("example.com") is False

def test_send_message_request_validation():
    """Verify SendMessageRequest schema and constraints."""
    # Valid model
    req = SendMessageRequest(chat="test_user", text="Hello world")
    assert req.chat == "test_user"
    assert req.text == "Hello world"

    # Empty chat should fail
    with pytest.raises(ValidationError):
        SendMessageRequest(chat="", text="Hello")

    # Empty text should fail
    with pytest.raises(ValidationError):
        SendMessageRequest(chat="test_user", text="")

    # Max length text validation
    SendMessageRequest(chat="test", text="a" * 4096)
    with pytest.raises(ValidationError):
        SendMessageRequest(chat="test", text="a" * 4097)

def test_wait_message_request_validation():
    """Verify WaitMessageRequest schema and constraints."""
    req = WaitMessageRequest(chat="bot_chat", after_message_id=10, timeout_seconds=15)
    assert req.chat == "bot_chat"
    assert req.after_message_id == 10
    assert req.timeout_seconds == 15

    # Defaults
    default_req = WaitMessageRequest(chat="bot_chat")
    assert default_req.after_message_id == 0
    assert default_req.timeout_seconds == 20

    # Negative after_message_id should fail
    with pytest.raises(ValidationError):
        WaitMessageRequest(chat="bot_chat", after_message_id=-1)

    # Invalid timeout bounds
    with pytest.raises(ValidationError):
        WaitMessageRequest(chat="bot_chat", timeout_seconds=0)
    with pytest.raises(ValidationError):
        WaitMessageRequest(chat="bot_chat", timeout_seconds=61)

def test_click_button_request_validation():
    """Verify ClickButtonRequest schema and constraints."""
    req = ClickButtonRequest(chat="bot", message_id=123, button_index=0)
    assert req.chat == "bot"
    assert req.message_id == 123
    assert req.button_index == 0

    # message_id must be >= 1
    with pytest.raises(ValidationError):
        ClickButtonRequest(chat="bot", message_id=0, button_index=0)
    with pytest.raises(ValidationError):
        ClickButtonRequest(chat="bot", message_id=-5, button_index=0)

    # button_index must be >= 0
    with pytest.raises(ValidationError):
        ClickButtonRequest(chat="bot", message_id=1, button_index=-1)

def test_parse_chat_target():
    """Verify parsing of chat identifiers (numeric IDs vs strings/usernames)."""
    assert parse_chat_target("12345") == 12345
    assert parse_chat_target("-100123456789") == -100123456789
    assert parse_chat_target("@mychannel") == "@mychannel"
    assert parse_chat_target("username") == "username"
    assert parse_chat_target(" +123456789 ") == 123456789

def test_serialize_message_structure():
    """Verify message serialization with mock object."""
    class DummyButton:
        def __init__(self, text):
            self.text = text

    class DummyMessage:
        def __init__(self):
            self.id = 42
            self.date = None
            self.sender_id = 999
            self.text = "Test text"
            self.out = False
            self.reply_to = None
            self.buttons = [[DummyButton("Btn1"), DummyButton("Btn2")], [DummyButton("Btn3")]]

    serialized = serialize_message(DummyMessage())
    assert serialized["id"] == 42
    assert serialized["sender_id"] == 999
    assert serialized["text"] == "Test text"
    assert serialized["out"] is False
    assert len(serialized["buttons"]) == 2
    assert serialized["buttons"][0][0] == {"text": "Btn1", "index": 0}
    assert serialized["buttons"][0][1] == {"text": "Btn2", "index": 1}
    assert serialized["buttons"][1][0] == {"text": "Btn3", "index": 2}

def test_auth_unauthorized_requests():
    """Verify HTTP 401 on missing or invalid Bearer tokens."""
    client = TestClient(app, raise_server_exceptions=False)

    # 1. Missing header
    resp = client.get("/health")
    assert resp.status_code == 401
    assert "detail" in resp.json()

    # 2. Invalid token
    resp = client.get("/health", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401

    # 3. Valid token
    resp = client.get("/health", headers={"Authorization": f"Bearer {API_TOKEN}"})
    # Client is authorized at REST level, returns 200 with telegram status
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "telegram_connected" in data
    assert "is_authorized" in data

def test_openapi_docs_disabled():
    """Verify that public OpenAPI docs and schemas are disabled or protected."""
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/docs")
    assert resp.status_code == 404
    resp = client.get("/redoc")
    assert resp.status_code == 404
    resp = client.get("/openapi.json")
    assert resp.status_code == 404
