import telebot
import datetime
import os
import time
import logging
import re
import threading
from threading import Timer, Lock
import asyncio
import subprocess

# Set up logging
logging.basicConfig(level=logging.INFO)

# =============================================================================
# 🔧 CONFIGURATION
# =============================================================================
OWNER_ID = "7119717262"
BOT_TOKEN = "8265293892:AAEyfiYiMuVW1VEHUrUx0YBg0mvBUkyFPw8"

# Global Constants
MAX_SESSION_DURATION = 60
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

# Async Setup for Countdowns
async_loop = asyncio.new_event_loop()
def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_async_loop, args=(async_loop,), daemon=True).start()

async def async_update_countdown(message, msg_id, start_time, duration, host, port, session_info):
    end_time = start_time + datetime.timedelta(seconds=duration)
    while True:
        remaining = (end_time - datetime.datetime.now()).total_seconds()
        if remaining <= 0: break
        try:
            bot.edit_message_text(
                chat_id=message.chat.id, message_id=msg_id,
                text=f"🚀 <b>DEPLOYMENT ACTIVE</b> 🚀\n\n💻 Host: <code>{host}</code>\n📡 Port: <code>{port}</code>\n⏳ Timer: <code>{int(remaining)}s</code>\n⚔️ Status: <b>Active</b>",
                parse_mode='HTML'
            )
        except: pass
        await asyncio.sleep(1.5)
    
    try:
        bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ <b>SESSION COMPLETED</b>\n💻 Host: <code>{host}</code>\n📡 Port: <code>{port}</code>", parse_mode='HTML')
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

    try:
        # Binary 'port' execution locally
        cmd = ["./port", host, port, str(duration), "900"]
        subprocess.Popen(cmd)
        
        session_info = {'end_time': datetime.datetime.now() + datetime.timedelta(seconds=duration)}
        active_sessions.append(session_info)
        
        msg = bot.send_message(
            message.chat.id, 
            f"⚡️ Initiating Deployment...\n💻 Host: {host}\n📡 Port: {port}", 
            parse_mode='HTML'
        )
        
        asyncio.run_coroutine_threadsafe(
            async_update_countdown(message, msg.message_id, datetime.datetime.now(), duration, host, port, session_info),
            async_loop
        )
    except Exception as e:
        logging.error(f"Execution error: {e}")
        bot.reply_to(message, "❌ Execution failed.")

@bot.message_handler(commands=['stop_session'])
def stop_session(message):
    if str(message.from_user.id) != OWNER_ID: return
    
    try:
        subprocess.run(["pkill", "-f", "port"])
        bot.reply_to(message, "🛑 Process terminated.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

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
        "🚀 <b>Management Console</b>\n\n"
        "<b>Commands:</b>\n"
        "/deploy &lt;host&gt; &lt;port&gt; &lt;time&gt;\n"
        "/stop_session\n"
        "/grant &lt;id&gt; &lt;days&gt;"
    )
    bot.reply_to(message, help_text, parse_mode='HTML')

# Polling Loop
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        time.sleep(5)
