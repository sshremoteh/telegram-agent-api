#!/usr/bin/env python3
"""
Stateful Negotiation & Auto-Responder Agent for Telegram Sales.
Maintains dialogue state and handles objections, bargains, and payment requests naturally.
"""
import asyncio
import logging
import os
import re
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

# Configurable payment details
PAYMENT_REQUISITES = os.getenv("PAYMENT_REQUISITES", "СБП / Т-Банк / Сбер по номеру или USDT TRC-20")

# States: PITCHING -> NEGOTIATING -> AWAITING_PAYMENT -> CLOSED
current_state = "AWAITING_PAYMENT"

def analyze_intent(text: str) -> str:
    t = text.lower()
    
    # Ready to pay / asking for details
    if any(w in t for w in ["куда", "кидать", "перевод", "карту", "карта", "счет", "номер", "реквизит", "сбп", "чек", "оплат", "скинь"]):
        return "READY_TO_PAY"
    
    # Bargain / price offer
    if re.search(r'\b(\d+)\s*(доллар|бакс|\$|рубл|к|usdt)\b', t) or any(w in t for w in ["сколько", "почем", "цена", "стоит", "дорого", "скидк", "дешев"]):
        return "PRICE_BARGAIN"
    
    # Acceptance
    if any(w in t for w in ["давай", "го", "ок", "ладно", "по рукам", "согласен", "хорошо"]):
        return "ACCEPT"
    
    # Questions / what is this
    if any(w in t for w in ["что это", "как это", "зачем", "покажи", "расскажи", "как работает"]):
        return "QUESTION_DETAILS"
    
    # Hard rejection
    if any(w in t for w in ["не хочу", "не надо", "нет", "отвали", "нафиг", "бред"]):
        return "REJECTION"
        
    return "GENERAL"

def generate_stateful_reply(text: str) -> str:
    global current_state
    intent = analyze_intent(text)
    logger.info("Detected intent: %s (Current state: %s)", intent, current_state)
    
    if intent == "READY_TO_PAY" or current_state == "AWAITING_PAYMENT":
        current_state = "AWAITING_PAYMENT"
        return (
            f"Вот реквизиты для перевода (10$ или 1000 руб):\n\n"
            f"💳 {PAYMENT_REQUISITES}\n\n"
            f"Как переведешь — скинь скрин или чек, и я сразу пришлю ссылку на архив с проектом и помогу запустить!"
        )
    
    if intent == "PRICE_BARGAIN":
        current_state = "AWAITING_PAYMENT"
        return (
            "По рукам, договорились за 10$ (1000 руб)! "
            "Отдаю полный доступ к репозиторию и настрою под тебя. "
            "Куда удобнее перевести — на карту (СБП) или криптой (USDT / TON)?"
        )
        
    if intent == "ACCEPT":
        current_state = "AWAITING_PAYMENT"
        return (
            "Отлично! Можешь перевести 1000 руб на карту (СБП) или 10 USDT. "
            "Напиши, какой способ удобнее, и я сразу пришлю реквизиты."
        )

    if intent == "QUESTION_DETAILS":
        return (
            "Смотри: этот сервер ставится локально и подключает твой Telegram к Claude, ChatGPT или Cursor через протокол MCP. "
            "ИИ сможет читать переписки, искать инфу, отправлять сообщения и автоматизировать любые рутинные задачи. "
            "Все работает прямо с твоего компа, безопасно и без блокировок."
        )

    if intent == "REJECTION":
        return (
            "Без проблем, не навязываю! Если позже понадобится автоматизировать Telegram через нейросети — напиши, всё настроим."
        )

    return (
        "Если готов забрать сетап за 10$ — напиши, куда скинуть реквизиты (карта или крипта), и сразу начнем!"
    )
