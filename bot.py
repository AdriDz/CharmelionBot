import asyncio
import asyncpg
import sys
import os
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"

DB_HOST = os.environ.get("DB_HOST", "db.uyegbzglcepchhydfoly.supabase.co")
DB_PASS = os.environ.get("DB_PASS", "Adrdia123.,@")
DB_USER = "postgres"
DB_NAME = "postgres"
DB_PORT = 5432

ADMINS = [1275539447, 425680448]
GROUP_ID = -1003712667390
BOT_USERNAME = "CharmelionBot"
CANAL_LINK = "https://t.me/TU_CANAL"

db_pool = None

# ── Base de datos ──────────────────────────────────────────────
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        ssl="require"
    )
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT
            )
        """)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT")
        except:
            pass

async def add_user(user_id, username, full_name):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, username, full_name)
               VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE
               SET username = $2, full_name = $3""",
            user_id, username, full_name
        )

async def get_users():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, full_name FROM users")
        return rows

# ── Helpers ────────────────────────────────────────────────────
def is_admin(update: Update):
    return update.effective_user.id in ADMINS

def format_user(row):
    name = row["full_name"] or "Sin nombre"
    username = f"@{row['username']}" if row["username"] else "sin @"
    return f"{name} ({username})"

async def notify_admins(bot, message):
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
        except:
            pass

async def broadcast_all(bot, message):
    users = await get_users()
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 30
    num_tanda = 1

    await notify_admins(bot, f"📤 *Iniciando envío*\n\n👥 Total usuarios: *{total}*\n📦 Tandas de 5 cada 30 segundos")

    for i in range(0, total, tanda_size):
        tanda = users[i:i + tanda_size]
        nombres_ok = []
        nombres_fail = []

        for row in tanda:
            try:
                await bot.send_message(
                    chat_id=row["user_id"],
                    text=message,
                    protect_content=True
                )
                enviados += 1
                nombres_ok.append(f"✅ {format_user(row)}")
                await asyncio.sleep(0.3)
            except:
                fallidos += 1
                nombres_fail.append(f"❌ {format_user(row)}")

        lista = "\n".join(nombres_ok + nombres_fail)
        await notify_admins(
            bot,
            f"📦 *Tanda {num_tanda}*\n\n"
            f"{lista}\n\n"
            f"📊 Progreso: *{enviados + fallidos}/{total}*"
        )
        num_tanda += 1

        if i + tanda_size < total:
            await asyncio.sleep(espera)

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
    user = update.effective_user
    await add_user(user.id, user.username or "", user.full_name or "")
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
    users = await get_users()
    await update.message.reply_text(
        f"👥 Usuarios registrados: *{len(users)}*",
        parse_mode="Markdown"
    )

# ── /lista ─────────────────────────────────────────────────────
async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    users = await get_users()
    if not users:
        await update.message.reply_text("No hay usuarios registrados aún.")
        return
    text = "👥 *Usuarios registrados:*\n\n"
    for row in users:
        text += f"• {format_user(row)}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /broadcast ─────────────────────────────────────────────────
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /broadcast mensaje")
        return
    message = " ".join(context.args)
    users = await get_users()
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
    users = await get_users()
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
        [InlineKeyboardButton("📲 Regístrate para recibir las apuestas",
                              url=f"https://t.me/{BOT_USERNAME}?start=registro")],
        [InlineKeyboardButton("📢 Ir al canal", url=CANAL_LINK)]
    ])
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="🎯 *¿Quieres recibir las apuestas antes que nadie?*\n\nRegístrate en el bot y te llegará directamente al privado.\nSin perderte nada. Sin retrasos. 🔔",
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
        text="💼 *¿Quieres patrocinar nuestro canal?*\n\nLlegamos a miles de usuarios interesados en apuestas.\nContacta con nosotros para más información. 📩",
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
        "/lista → ver todos los usuarios con nombre\n"
        "/id → ver el ID de un chat\n"
        "/ayuda → ver esta lista",
        parse_mode="Markdown"
    )

# ── Arranque ───────────────────────────────────────────────────
async def on_startup(app):
    await init_db()
    await notify_admins(app.bot, "🟢 *Bot iniciado correctamente*\n\nEl bot está activo y listo.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("id",         get_id))
    app.add_handler(CommandHandler("total",      total))
    app.add_handler(CommandHandler("lista",      lista))
    app.add_handler(CommandHandler("broadcast",  broadcast))
    app.add_handler(CommandHandler("anuncio",    anuncio))
    app.add_handler(CommandHandler("patrocinar", patrocinar))
    app.add_handler(CommandHandler("ayuda",      ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_directo))

    print("🤖 Bot corriendo...")
    app.run_polling()