import sqlite3
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"

# ── Vosotros dos (añade el ID de tu amigo cuando lo tengas) ──
ADMINS = [
    1275539447,   # tu ID
    425680448,  # ID de tu amigo — descomenta y pon su ID aquí
]

GROUP_ID = -1001234567890  # Reemplaza con el ID real del grupo (usa /id en el grupo)
BOT_USERNAME = "CharmelionBot"  # Sin @

CANAL_LINK = "https://t.me/TU_CANAL"  # Reemplaza con el link de tu canal

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

# ── Helpers ────────────────────────────────────────────────────

def is_admin(update: Update):
    return update.effective_user.id in ADMINS

async def broadcast_all(bot, message):
    users = get_users()
    enviados = 0
    for user_id in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=message,
                protect_content=True  # 🔒 No se puede reenviar
            )
            enviados += 1
            await asyncio.sleep(0.08)
        except:
            pass
    return enviados

# ── /start — cualquier persona puede registrarse ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    await update.message.reply_text(
        "✅ *Te has registrado correctamente.*\n\n"
        "Ahora recibirás las apuestas y avisos importantes directamente aquí.\n\n"
        f"📢 Síguenos también en el canal: {CANAL_LINK}",
        parse_mode="Markdown"
    )

# ── /id — muestra el ID del chat ───────────────────────────────
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID de este chat: `{update.effective_chat.id}`", parse_mode="Markdown")

# ── /total — usuarios registrados (solo admins) ────────────────
async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    users = get_users()
    await update.message.reply_text(f"👥 Usuarios registrados: *{len(users)}*", parse_mode="Markdown")

# ── /broadcast — manda mensaje a todos (solo admins) ──────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /broadcast mensaje")
        return
    message = " ".join(context.args)
    await update.message.reply_text("⏳ Enviando...")
    enviados = await broadcast_all(context.bot, message)
    await update.message.reply_text(f"✅ Enviado a *{enviados}* usuarios", parse_mode="Markdown")

# ── Mensaje directo — cualquier texto del admin se manda a todos
async def mensaje_directo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return  # ignora completamente a los demás
    message = update.message.text
    await update.message.reply_text("⏳ Enviando a todos los usuarios...")
    enviados = await broadcast_all(context.bot, message)
    await update.message.reply_text(f"✅ Enviado a *{enviados}* usuarios", parse_mode="Markdown")

# ── /anuncio — botón de registro al grupo (solo admins) ───────
async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📲 Regístrate para recibir las apuestas",
            url=f"https://t.me/{BOT_USERNAME}?start=registro"
        )],
        [InlineKeyboardButton(
            "📢 Ir al canal",
            url=CANAL_LINK
        )]
    ])
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=(
            "🎯 *¿Quieres recibir las apuestas antes que nadie?*\n\n"
            "Regístrate en el bot y te llegará directamente al privado.\n"
            "Sin perderte nada. Sin retrasos. 🔔"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await update.message.reply_text("✅ Anuncio enviado al grupo")

# ── /patrocinar — mensaje de patrocinio al grupo (solo admins) ─
async def patrocinar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Patrocinar el canal", url=CANAL_LINK)]
    ])
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=(
            "💼 *¿Quieres patrocinar nuestro canal?*\n\n"
            "Llegamos a miles de usuarios interesados en apuestas.\n"
            "Contacta con nosotros para más información. 📩"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await update.message.reply_text("✅ Mensaje de patrocinio enviado")

# ── /ayuda — lista de comandos (solo admins) ──────────────────
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "✉️ *Escribir cualquier mensaje* → se manda a todos los registrados\n"
        "/broadcast mensaje → igual que escribir directamente\n"
        "/anuncio → manda botón de registro al grupo\n"
        "/patrocinar → manda mensaje de patrocinio al grupo\n"
        "/total → ver cuántos usuarios registrados\n"
        "/id → ver el ID de un chat\n"
        "/ayuda → ver esta lista",
        parse_mode="Markdown"
    )

# ── Arranque ───────────────────────────────────────────────────
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("id",         get_id))
    app.add_handler(CommandHandler("total",      total))
    app.add_handler(CommandHandler("broadcast",  broadcast))
    app.add_handler(CommandHandler("anuncio",    anuncio))
    app.add_handler(CommandHandler("patrocinar", patrocinar))
    app.add_handler(CommandHandler("ayuda",      ayuda))

    # Cualquier mensaje de texto del admin se manda a todos
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_directo))

    print("🤖 Bot corriendo...")
    app.run_polling()