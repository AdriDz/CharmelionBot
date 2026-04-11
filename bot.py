import sqlite3
import asyncio
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"
ADMIN_ID = 1275539447
GROUP_ID = -1001234567890  # Reemplaza con tu GROUP_ID real (usa /id en el grupo)
BOT_USERNAME = "CharmelionBot"  # Reemplaza con el username de tu bot (sin @)

# ── Base de datos ──────────────────────────────────────────────
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()

def add_user(user_id):
    try:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except:
        pass

def get_users():
    cursor.execute("SELECT user_id FROM users")
    return [row[0] for row in cursor.fetchall()]

# ── Comandos del bot ───────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    await update.message.reply_text(
        "✅ Te has registrado correctamente.\nAhora recibirás los avisos importantes."
    )

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = get_users()
    await update.message.reply_text(f"👥 Usuarios registrados: {len(users)}")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID de este chat: {update.effective_chat.id}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No autorizado")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /broadcast mensaje")
        return
    message = " ".join(context.args)
    await _broadcast_message(context.bot, message)
    await update.message.reply_text("✅ Mensaje enviado a todos los usuarios")

async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await _send_group_register_button(context.bot)
    await update.message.reply_text("✅ Botón de registro enviado al grupo")

async def sendgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /sendgroup mensaje")
        return
    message = " ".join(context.args)
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=message,
        protect_content=True
    )
    await update.message.reply_text("✅ Mensaje enviado al grupo")

# ── Funciones auxiliares ───────────────────────────────────────

async def _broadcast_message(bot, message):
    users = get_users()
    for user_id in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=message,
                protect_content=True
            )
            await asyncio.sleep(0.08)
        except:
            pass

async def _send_group_register_button(bot):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📲 Pulsa aquí para registrarte",
            url=f"https://t.me/{BOT_USERNAME}?start=registro"
        )]
    ])
    await bot.send_message(
        chat_id=GROUP_ID,
        text=(
            "👇 *Regístrate para recibir avisos importantes*\n\n"
            "Pulsa el botón de abajo, abre el bot y dale a /start."
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
        protect_content=False
    )

# ── Flask API ─────────────────────────────────────────────────

flask_app = Flask(__name__)
CORS(flask_app)
bot_app = None

@flask_app.route("/api/broadcast", methods=["POST"])
def api_broadcast():
    data = request.json
    if data.get("token") != str(ADMIN_ID):
        return jsonify({"error": "No autorizado"}), 403
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400
    asyncio.run_coroutine_threadsafe(
        _broadcast_message(bot_app.bot, message),
        bot_app.loop
    )
    return jsonify({"ok": True, "users": len(get_users())})

@flask_app.route("/api/sendgroup", methods=["POST"])
def api_sendgroup():
    data = request.json
    if data.get("token") != str(ADMIN_ID):
        return jsonify({"error": "No autorizado"}), 403
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400
    asyncio.run_coroutine_threadsafe(
        bot_app.bot.send_message(chat_id=GROUP_ID, text=message, protect_content=True),
        bot_app.loop
    )
    return jsonify({"ok": True})

@flask_app.route("/api/anuncio", methods=["POST"])
def api_anuncio():
    data = request.json
    if data.get("token") != str(ADMIN_ID):
        return jsonify({"error": "No autorizado"}), 403
    asyncio.run_coroutine_threadsafe(
        _send_group_register_button(bot_app.bot),
        bot_app.loop
    )
    return jsonify({"ok": True})

@flask_app.route("/api/stats", methods=["GET"])
def api_stats():
    token = request.args.get("token")
    if token != str(ADMIN_ID):
        return jsonify({"error": "No autorizado"}), 403
    return jsonify({"users": len(get_users())})

def run_flask():
    flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# ── Arranque ───────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).build()
    bot_app = app

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("total",     total))
    app.add_handler(CommandHandler("id",        get_id))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("anuncio",   anuncio))
    app.add_handler(CommandHandler("sendgroup", sendgroup))

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    print("🤖 Bot corriendo en http://localhost:5000")
    app.run_polling()