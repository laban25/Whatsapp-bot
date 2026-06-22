import os
import time
import logging
import anthropic
import requests
from dotenv import load_dotenv
from collections import defaultdict, deque

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
ID_INSTANCE        = os.getenv("GREEN_API_ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("GREEN_API_TOKEN_INSTANCE")
BOT_NAME           = os.getenv("BOT_NAME", "My Assistant")
MAX_HISTORY        = int(os.getenv("MAX_HISTORY", 10))

BASE_URL = f"https://api.green-api.com/waInstance{ID_INSTANCE}"

ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
history = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))

def receive_notification():
    try:
        r = requests.get(f"{BASE_URL}/receiveNotification/{API_TOKEN_INSTANCE}", timeout=20)
        r.raise_for_status()
        return r.json()
    except:
        return None

def delete_notification(receipt_id):
    try:
        requests.delete(f"{BASE_URL}/deleteNotification/{API_TOKEN_INSTANCE}/{receipt_id}", timeout=10)
    except:
        pass

def send_message(chat_id, text):
    try:
        requests.post(f"{BASE_URL}/sendMessage/{API_TOKEN_INSTANCE}", json={"chatId": chat_id, "message": text}, timeout=15)
    except:
        pass

def build_system_prompt():
    from datetime import date
    return (f"You are {BOT_NAME}, a helpful WhatsApp assistant.\n"
            "Keep replies concise. Use plain text only.\n"
            f"Today: {date.today().strftime('%A, %d %B %Y')}.")

def get_ai_reply(chat_id, user_message):
    history[chat_id].append({"role": "user", "content": user_message})
    response = ai_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=build_system_prompt(),
        messages=list(history[chat_id]),
    )
    reply = response.content[0].text
    history[chat_id].append({"role": "assistant", "content": reply})
    return reply

def handle_command(chat_id, text):
    cmd = text.strip().lower()
    if cmd == "/reset":
        history[chat_id].clear()
        return "🔄 Conversation reset!"
    if cmd == "/help":
        return "🤖 Commands:\n/reset — Clear history\n/help — Show commands\n\nJust type anything to chat!"
    return None

def process_notification(notification):
    body = notification.get("body", {})
    if body.get("typeWebhook") != "incomingMessageReceived":
        return
    if body.get("messageData", {}).get("typeMessage") != "textMessage":
        return
    chat_id = body.get("senderData", {}).get("chatId", "")
    text = body.get("messageData", {}).get("textMessageData", {}).get("textMessage", "").strip()
    if "@g.us" in chat_id or not text:
        return
    log.info("📩 [%s]: %s", chat_id, text)
    reply = handle_command(chat_id, text)
    if not reply:
        try:
            reply = get_ai_reply(chat_id, text)
        except Exception as e:
            reply = "Sorry, I ran into an error. Please try again."
            log.error("AI error: %s", e)
    send_message(chat_id, reply)

def run():
    
    log.info("🚀 %s is starting...", BOT_NAME)
    while True:
        try:
            notification = receive_notification()
            if not notification:
                time.sleep(2)
                continue
            receipt_id = notification.get("receiptId")
            log.info("📬 Got notification: %s", str(notification)[:200])
            try:
                process_notification(notification)
            except Exception as e:
                log.exception("Error: %s", e)
            finally:
                if receipt_id:
                    delete_notification(receipt_id)
        except Exception as e:
            log.error("Loop error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    run()
