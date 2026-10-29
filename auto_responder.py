#!/usr/bin/env python3
"""
Background Auto-Responder for @sinorias.
Monitors chat history and handles negotiation automatically.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
LOG_FILE = BASE_DIR / "auto_responder.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("auto_responder")

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

API_HOST = os.getenv("API_HOST", "127.0.0.1").strip()
API_PORT = int(os.getenv("API_PORT", "8765"))
API_TOKEN = os.getenv("API_TOKEN", "").strip()
BASE_URL = f"http://{API_HOST}:{API_PORT}"
TARGET_CHAT = "sinorias"

def generate_counter_pitch(incoming_text: str) -> str:
    text_lower = incoming_text.lower()
    
    # Negative responses: "не хочу", "не надо", "нет", "отстань", etc.
    if any(w in text_lower for w in ["не хочу", "не надо", "нет", "зачем", "нафиг", "отвали", "пофиг", "неинтересно"]):
        return (
            "Да брось, это не очередная спам-тема или бесполезная подписка. "
            "MCP дает прямой мост между твоей телегой и ИИ (Claude / ChatGPT / Antigravity). "
            "Агент может сам мониторить каналы, делать выжимки, фильтровать спам и отвечать по сценариям, "
            "пока ты занят другими делами. Экономит кучу времени. "
            "Хочешь, просто покажу демку вживую — сам увидишь, как это ускоряет работу?"
        )
    
    # Price inquiry
    if any(w in text_lower for w in ["сколько", "почем", "цена", "стоит", "прайс", "рубл", "usdt", "$"]):
        return (
            "По цене договоримся чисто символически, отдам со скидкой и помогу развернуть всё под ключ за 10 минут. "
            "Тебе в первую очередь для каких задач — автоматизация переписок, парсинг каналов или свои боты?"
        )
    
    # What is it / details inquiry
    if any(w in text_lower for w in ["что это", "как работает", "расскажи", "подробнее", "че за", "что такое"]):
        return (
            "Смотри: MCP (Model Context Protocol) — это открытый стандарт, который позволяет нейросети напрямую "
            "управлять Telegram-клиентом. Ты просто пишешь ИИ задачу на обычном языке, а он сам читает нужные чаты, "
            "собирает инфу, отправляет сообщения и кликает кнопки. Всё работает локально на твоей машине, данные никому не утекают."
        )
    
    # Default persuasive reply
    return (
        "Понял тебя. Но штука реально уникальная: сейчас вся индустрия переходит на агентские фреймворки, "
        "и локальный Telegram MCP — это самый простой способ заставить ИИ работать на тебя в фоне. "
        "Если передумаешь или захочешь взглянуть на код/документацию — маякни, скину посмотреть без обязательств!"
    )

async def monitor_loop():
    logger.info("Auto-responder started for chat: %s", TARGET_CHAT)
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    last_processed_id = 9138
    
    # First, get latest message ID to calibrate
    async with httpx.AsyncClient(trust_env=False, timeout=20.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/history", headers=headers, params={"chat": TARGET_CHAT, "limit": 5})
            if resp.status_code == 200:
                msgs = resp.json().get("messages", [])
                if msgs:
                    max_id = max(m["id"] for m in msgs)
                    last_processed_id = max(last_processed_id, max_id)
                    logger.info("Calibrated last_processed_id to: %d", last_processed_id)
        except Exception as e:
            logger.error("Initial calibration error: %s", e)

    while True:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=25.0) as client:
                resp = await client.get(f"{BASE_URL}/history", headers=headers, params={"chat": TARGET_CHAT, "limit": 10})
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data.get("messages", [])
                    # Look for new incoming messages
                    incoming = [m for m in messages if m["id"] > last_processed_id and not m.get("out", False)]
                    
                    if incoming:
                        # Sort ascending
                        incoming.sort(key=lambda m: m["id"])
                        for msg in incoming:
                            msg_id = msg["id"]
                            msg_text = msg.get("text", "").strip()
                            logger.info("[NEW INCOMING MESSAGE #%d]: %s", msg_id, msg_text)
                            
                            # Generate persuasive response
                            reply = generate_counter_pitch(msg_text)
                            logger.info("Sending persuasive reply to #%d...", msg_id)
                            
                            send_resp = await client.post(
                                f"{BASE_URL}/send",
                                headers=headers,
                                json={"chat": TARGET_CHAT, "text": reply}
                            )
                            if send_resp.status_code == 200:
                                sent_info = send_resp.json()
                                logger.info("[REPLY SENT #%d]: %s", sent_info.get("id"), reply[:60] + "...")
                                last_processed_id = max(last_processed_id, sent_info.get("id", msg_id))
                            else:
                                logger.error("Failed to send reply: %s", send_resp.text)
                                last_processed_id = max(last_processed_id, msg_id)
                    else:
                        # Update last_processed_id to latest outgoing if any
                        if messages:
                            max_id = max(m["id"] for m in messages)
                            last_processed_id = max(last_processed_id, max_id)
                            
        except Exception as e:
            logger.error("Poll cycle error: %s", e)
        
        await asyncio.sleep(12)

if __name__ == "__main__":
    asyncio.run(monitor_loop())
