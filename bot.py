import os
import time
import logging
import anthropic
import requests
from dotenv import load_dotenv
from collections import defaultdict, deque

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
ID_INSTANCE        = os.getenv("GREEN_API_ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("GREEN_API_TOKEN_INSTANCE")
BOT_NAME           = os.getenv("BOT_NAME", "My Assistant")
MAX_HISTORY        = int(os.getenv("MAX_HISTORY", 10))
BASE_URL           = f"https://api.green-api.com/waInstance{ID_INSTANCE}"

ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
history = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))

def receive_notification():
    try:
        r = requests.get(f"{BASE_URL}/receiveNotification/{API_TOKEN_INSTANCE}", timeout=20)
        r.raise_for_status()
        data = r.json()
        if data:
            log.info("📬 RAW: %s", str(data)[:500])
        return data
    except Exception as e:
        log.error("receive error: %s", e)
        return None

def delete_notification(receipt_id):
    try:
        requests.delete(f"{BASE_URL}/deleteNotification/{API_TOKEN_INSTANCE}/{receipt_id}", timeout=10)
        log.info("🗑️ Deleted receipt %s", receipt_id)
    except Exception as e:
        log.error("delete error: %s", e)

def send_message(chat_id, text):
    try:
        r = requests.post(f"{BASE_URL}/sendMessage/{API_TOKEN_INSTANCE}",
                         json={"chatId": chat_id, "message": text}, timeout=15)
        log.info("📤 Sent to %s: status=%s", chat_id, r.status_code)
    except Exception as e:
        log.error("send error: %s", e)

def get_ai_reply(chat_id, user_message):
    history[chat_id].append({"role": "user", "content": user_message})
    response = ai_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=f"You are {BOT_NAME}, a helpful WhatsApp assistant. Keep replies short and friendly.",
        messages=list(history[chat_id]),
    )
    reply = response.content[0].text
    history[chat_id].append({"role": "assistant", "content": reply})
    return reply

def process_notification(notification):
    body = notification.get("body", {})
    webhook_type = body.get("typeWebhook", "")
    log.info("📋 typeWebhook: %s", webhook_type)

    if webhook_type != "incomingMessageReceived":
        log.info("⏭️ Skipping type: %s", webhook_type)
        return

    msg_type = body.get("messageData", {}).get("typeMessage", "")
    log.info("📋 typeMessage: %s", msg_type)

    if msg_type != "textMessage":
        log.info("⏭️ Skipping message type: %s", msg_type)
        return

    chat_id = body.get("senderData", {}).get("chatId", "")
    text = body.get("messageData", {}).get("textMessageData", {}).get("textMessage", "").strip()

    log.info("📩 From: %s | Text: %s", chat_id, text)

    if "@g.us" in chat_id:
        log.info("⏭️ Skipping group message")
        return

    if not text:
        log.info("⏭️ Skipping empty text")
        return

    try:
        reply = get_ai_reply(chat_id, text)
        send_message(chat_id, reply)
        log.info("✅ Replied to %s", chat_id)
    except Exception as e:
        log.error("❌ Error: %s", e)
        send_message(chat_id, "Sorry, I ran into an error. Please try again.")

def run():
    log.info("🚀 %s is starting...", BOT_NAME)
    while True:
        try:
            notification = receive_notification()
            if not notification:
                time.sleep(2)
                continue
            receipt_id = notification.get("receiptId")
            process_notification(notification)
            if receipt_id:
                delete_notification(receipt_id)
        except Exception as e:
            log.error("Loop error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    run()
