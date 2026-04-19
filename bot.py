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

def format_user(row):
    return f"{row['full_name'] or 'Sin nombre'} (@{row['username'] or 'sin @'})"

# ========================
# LÓGICA DE ENVÍO (MULTITAREA)
# ========================
async def ejecutar_broadcast_en_fondo(bot, message):
    users = list(await get_users())
    random.shuffle(users)
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 120 # Segundos entre tandas
    
    await bot.send_message(chat_id=ADMINS[0], text=f"🚀 *Iniciando nuevo envío:*\n{message[:50]}...")

    for i in range(0, total, tanda_size):
        tanda = users[i:i + tanda_size]
        for row in tanda:
            try:
                await bot.send_message(chat_id=row["user_id"], text=message, protect_content=True)
                enviados += 1
            except:
                fallidos += 1
            await asyncio.sleep(0.3)
        
        if i + tanda_size < total:
            await asyncio.sleep(espera)

    await bot.send_message(chat_id=ADMINS[0], text=f"🏁 *Envío completado*\n✅: {enviados} | ❌: {fallidos}")

# ========================
# COMANDOS Y HANDLERS
# ========================
def is_admin(update: Update): return update.effective_user.id in ADMINS

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
    text = "👥 *Usuarios registrados:*\n\n" + "\n".join([f"• {format_user(r)}" for r in users])
    await update.message.reply_text(text[:4000], parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.message.reply_text("⚠️ Usa: /broadcast mensaje")
        return
    msg = " ".join(context.args)
    asyncio.create_task(ejecutar_broadcast_en_fondo(context.bot, msg))
    await update.message.reply_text("🚀 *Apuesta en cola.* Procesando en segundo plano.")

async def mensaje_directo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    asyncio.create_task(ejecutar_broadcast_en_fondo(context.bot, update.message.text))
    await update.message.reply_text("🚀 *Mensaje en cola.* Procesando en segundo plano.")

async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 Regístrate", url=f"https://t.me/{BOT_USERNAME}?start=registro")],
        [InlineKeyboardButton("📢 Canal", url=CANAL_LINK)]
    ])
    await context.bot.send_message(chat_id=GROUP_ID, text="🎯 *¿Quieres recibir apuestas?* Regístrate aquí.", reply_markup=kb)
    await update.message.reply_text("✅ Anuncio enviado")

async def patrocinar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Patrocinar", url=CANAL_LINK)]])
    await context.bot.send_message(chat_id=GROUP_ID, text="💼 *¿Quieres patrocinar el canal?*", reply_markup=kb)
    await update.message.reply_text("✅ Mensaje enviado")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text("📋 *Comandos:* /broadcast, /anuncio, /patrocinar, /total, /lista, /id, /ayuda")

# ========================
# EJECUCIÓN
# ========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).post_init(lambda app: init_db()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("anuncio", anuncio))
    app.add_handler(CommandHandler("patrocinar", patrocinar))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_directo))
    app.run_polling()