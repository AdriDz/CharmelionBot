import asyncio
import asyncpg
import random
import sys
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========================
# CONFIGURACIÓN
# ========================
TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMINS = [1275539447, 425680448]
GROUP_ID = -1003712667390
BOT_USERNAME = "CharmelionBot"
CANAL_LINK = "https://t.me/TU_CANAL"

db_pool = None
broadcast_counter = 0

# ========================
# BASE DE DATOS
# ========================
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT
            )
        """)

async def add_user(user_id, username, full_name):
    async with db_pool.acquire() as conn:
        await conn.execute("""INSERT INTO users (user_id, username, full_name)
                             VALUES ($1, $2, $3)
                             ON CONFLICT (user_id) DO UPDATE
                             SET username = $2, full_name = $3""", user_id, username, full_name)

async def get_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, full_name FROM users")

async def delete_all_users():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM users")

def format_user(row):
    return f"{row['full_name'] or 'Sin nombre'} (@{row['username'] or 'sin @'})"

def is_admin(update: Update): return update.effective_user.id in ADMINS

async def notify_admins(bot, message):
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
        except:
            pass

# ========================
# LÓGICA DE ENVÍO EN PARALELO
# ========================
async def broadcast_logic(bot, msg, broadcast_id):
    users = list(await get_users())
    random.shuffle(users)
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 120

    await notify_admins(bot,
        f"🚀 *Broadcast #{broadcast_id} iniciado* ({total} usuarios)\n📦 Tandas de 5 cada 2 minutos"
    )

    for i in range(0, total, tanda_size):
        tanda = users[i:i + tanda_size]
        nombres_ok = []
        nombres_fail = []

        for row in tanda:
            try:
                if msg.photo:
                    await bot.send_photo(chat_id=row["user_id"], photo=msg.photo[-1].file_id, caption=msg.caption, protect_content=True)
                elif msg.video:
                    await bot.send_video(chat_id=row["user_id"], video=msg.video.file_id, caption=msg.caption, protect_content=True)
                elif msg.document:
                    await bot.send_document(chat_id=row["user_id"], document=msg.document.file_id, caption=msg.caption, protect_content=True)
                else:
                    await bot.send_message(chat_id=row["user_id"], text=msg.text, protect_content=True)
                enviados += 1
                nombres_ok.append(f"✅ {format_user(row)}")
            except:
                fallidos += 1
                nombres_fail.append(f"❌ {format_user(row)}")
            await asyncio.sleep(0.3)

        lista = "\n".join(nombres_ok + nombres_fail)
        await notify_admins(bot,
            f"📦 *Broadcast #{broadcast_id} — Tanda {i // tanda_size + 1}*\n\n{lista}\n\n📊 Progreso: *{enviados + fallidos}/{total}*"
        )

        if i + tanda_size < total:
            await asyncio.sleep(espera)

    await notify_admins(bot,
        f"🏁 *Broadcast #{broadcast_id} finalizado*\n✅ Enviados: *{enviados}*\n❌ Fallidos: *{fallidos}*\n👥 Total: *{total}*"
    )

async def encolar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global broadcast_counter
    if not is_admin(update): return
    broadcast_counter += 1
    bid = broadcast_counter
    asyncio.create_task(broadcast_logic(context.bot, update.message, bid))
    await update.message.reply_text(f"🚀 *Broadcast #{bid} lanzado en paralelo*", parse_mode="Markdown")

# ========================
# COMANDOS
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user.id, user.username or "", user.full_name or "")
    await update.message.reply_text("✅ *Te has registrado correctamente.*", parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID: `{update.effective_chat.id}`", parse_mode="Markdown")

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    users = await get_users()
    await update.message.reply_text(f"👥 Usuarios: *{len(users)}*", parse_mode="Markdown")

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    users = await get_users()
    if not users:
        await update.message.reply_text("No hay usuarios registrados aún.")
        return
    text = "👥 *Usuarios registrados:*\n\n" + "\n".join([f"• {format_user(r)}" for r in users])
    await update.message.reply_text(text[:4000], parse_mode="Markdown")

async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Regístrate", url=f"https://t.me/{BOT_USERNAME}?start=registro")],
        [InlineKeyboardButton("📢 Canal", url=CANAL_LINK)]
    ])
    await context.bot.send_message(chat_id=GROUP_ID,
        text="🎯 *¿Quieres recibir apuestas antes que nadie?*\n\nRegístrate y te llegará directo al privado. 🔔",
        parse_mode="Markdown", reply_markup=kb)
    await update.message.reply_text("✅ Anuncio enviado")

async def patrocinar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Patrocinar", url=CANAL_LINK)]])
    await context.bot.send_message(chat_id=GROUP_ID,
        text="💼 *¿Quieres patrocinar el canal?*\n\nContacta con nosotros. 📩",
        parse_mode="Markdown", reply_markup=kb)
    await update.message.reply_text("✅ Mensaje enviado")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if update.effective_user.id != ADMINS[1]:
        await update.message.reply_text("⛔ No tienes permiso para ejecutar este comando.")
        return
    users = await get_users()
    total_antes = len(users)
    await delete_all_users()
    await update.message.reply_text(
        f"🗑️ *Base de datos limpiada*\n\n"
        f"Se han eliminado *{total_antes}* usuarios.\n"
        f"El bot está listo para un nuevo mes.",
        parse_mode="Markdown"
    )
    await notify_admins(context.bot,
        f"🗑️ *Reset ejecutado*\n\nSe han eliminado *{total_antes}* usuarios."
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "✉️ *Escribir cualquier mensaje* → broadcast en paralelo\n"
        "🖼️ *Foto/vídeo/documento* → también se manda a todos\n"
        "📊 *Cada broadcast tiene su número* para identificarlo\n\n"
        "/anuncio → manda botón de registro al grupo\n"
        "/patrocinar → manda mensaje de patrocinio\n"
        "/total → ver cuántos usuarios registrados\n"
        "/lista → ver todos los usuarios\n"
        "/reset → eliminar todos los usuarios\n"
        "/id → ver el ID de un chat\n"
        "/ayuda → ver esta lista",
        parse_mode="Markdown"
    )

async def on_startup(app):
    await init_db()
    await notify_admins(app.bot, "🟢 *Bot iniciado correctamente*\n\nEl bot está activo y listo.")

# ========================
# EJECUCIÓN
# ========================
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("id",         get_id))
    app.add_handler(CommandHandler("total",      total))
    app.add_handler(CommandHandler("lista",      lista))
    app.add_handler(CommandHandler("anuncio",    anuncio))
    app.add_handler(CommandHandler("patrocinar", patrocinar))
    app.add_handler(CommandHandler("reset",      reset))
    app.add_handler(CommandHandler("ayuda",      ayuda))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, encolar))

    print("🤖 Bot corriendo...")
    app.run_polling()