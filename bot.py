import sqlite3
import asyncio
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"

ADMINS = [
    1275539447,
    425680448,
]

GROUP_ID = -1003712667390
BOT_USERNAME = "CharmelionBot"
CANAL_LINK = "https://t.me/TU_CANAL"

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

def is_admin(update: Update):
    return update.effective_user.id in ADMINS

async def notify_admins(bot, message):
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
        except:
            pass

# ── Broadcast con bucle y reporte por tanda ───────────────────
async def broadcast_all(bot, message):
    users = get_users()
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 30  # segundos entre tandas
    num_tanda = 1

    await notify_admins(bot, f"📤 *Iniciando envío*\n\n👥 Total usuarios: *{total}*\n📦 Tandas de 5 cada 30 segundos")

    for i in range(0, total, tanda_size):
        tanda = users[i:i + tanda_size]

        for user_id in tanda:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    protect_content=True
                )
                enviados += 1
                await asyncio.sleep(0.3)
            except:
                fallidos += 1

        # Reporte de esta tanda a los admins
        await notify_admins(
            bot,
            f"📦 *Tanda {num_tanda} completada*\n\n"
            f"✅ Enviados hasta ahora: *{enviados}*\n"
            f"❌ Fallidos: *{fallidos}*\n"
            f"📊 Progreso: *{enviados + fallidos}/{total}*"
        )
        num_tanda += 1

        # Si quedan más usuarios, espera 30 segundos
        if i + tanda_size < total:
            await asyncio.sleep(espera)

    # Resumen final
    await notify_admins(
        bot,
        f"🏁 *Broadcast completado*\n\n"
        f"✅ Enviados: *{enviados}*\n"
        f"❌ Fallidos: *{fallidos}*\n"
        f"👥 Total: *{total}*"
    )

    return enviados, fallidos

# ── /start ─────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    await update.message.reply_text(
        "✅ *Te has registrado correctamente.*\n\n"
        "Ahora recibirás las apuestas y avisos importantes directamente aquí.\n\n"
        f"📢 Síguenos también en el canal: {CANAL_LINK}",
        parse_mode="Markdown"
    )

# ── /id ────────────────────────────────────────────────────────
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 ID de este chat: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

# ── /total ─────────────────────────────────────────────────────
async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    users = get_users()
    await update.message.reply_text(
        f"👥 Usuarios registrados: *{len(users)}*",
        parse_mode="Markdown"
    )

# ── /broadcast ─────────────────────────────────────────────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /broadcast mensaje")
        return
    message = " ".join(context.args)
    users = get_users()
    await update.message.reply_text(
        f"⏳ Iniciando envío a *{len(users)}* usuarios...",
        parse_mode="Markdown"
    )
    await broadcast_all(context.bot, message)

# ── Mensaje directo ────────────────────────────────────────────
async def mensaje_directo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    message = update.message.text
    users = get_users()
    await update.message.reply_text(
        f"⏳ Iniciando envío a *{len(users)}* usuarios...",
        parse_mode="Markdown"
    )
    await broadcast_all(context.bot, message)

# ── /anuncio ───────────────────────────────────────────────────
async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📲 Regístrate para recibir las apuestas",
            url=f"https://t.me/{BOT_USERNAME}?start=registro"
        )],
        [InlineKeyboardButton("📢 Ir al canal", url=CANAL_LINK)]
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

# ── /patrocinar ────────────────────────────────────────────────
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

# ── /ayuda ─────────────────────────────────────────────────────
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "✉️ *Escribir cualquier mensaje* → se manda a todos en tandas de 5\n"
        "/broadcast mensaje → igual que escribir directamente\n"
        "/anuncio → manda botón de registro al grupo\n"
        "/patrocinar → manda mensaje de patrocinio al grupo\n"
        "/total → ver cuántos usuarios registrados\n"
        "/id → ver el ID de un chat\n"
        "/ayuda → ver esta lista",
        parse_mode="Markdown"
    )

# ── Aviso arranque ─────────────────────────────────────────────
async def on_startup(app):
    await notify_admins(
        app.bot,
        "🟢 *Bot iniciado correctamente*\n\nEl bot está activo y listo."
    )

# ── Arranque ───────────────────────────────────────────────────
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("id",         get_id))
    app.add_handler(CommandHandler("total",      total))
    app.add_handler(CommandHandler("broadcast",  broadcast))
    app.add_handler(CommandHandler("anuncio",    anuncio))
    app.add_handler(CommandHandler("patrocinar", patrocinar))
    app.add_handler(CommandHandler("ayuda",      ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_directo))

    print("🤖 Bot corriendo...")
    app.run_polling()