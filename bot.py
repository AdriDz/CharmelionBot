import asyncio
import asyncpg
import random
import sys
import os
import secrets
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========================
# CONFIGURACIÓN
# ========================
TOKEN = "8623515567:AAFzx6xKFA-WSUQzDc5AkfpwZC3MICB6eJw"
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMINS = [425680448]
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
                full_name TEXT,
                expiry DATE
            )
        """)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry DATE
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                code TEXT PRIMARY KEY,
                used BOOLEAN DEFAULT FALSE,
                used_by BIGINT,
                expiry DATE
            )
        """)

async def get_users():
    """Devuelve usuarios activos (expiry vigente O sin expiry = usuarios de antes del sistema de códigos)"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT user_id, username, full_name FROM users
            WHERE expiry IS NULL OR expiry >= $1
        """, date.today())

async def get_all_users():
    """Devuelve todos los usuarios sin filtrar (para /lista y /total)"""
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id, username, full_name, expiry FROM users")

async def delete_all_users():
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM users")

async def is_user_active(user_id):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT expiry FROM users WHERE user_id = $1", user_id)
        if not row:
            return False
        # Sin expiry = usuario antiguo de abril, se considera activo hasta el reset
        if not row["expiry"]:
            return True
        return row["expiry"] >= date.today()

async def create_code(conn, days=31):
    code = secrets.token_hex(4).upper()
    expiry = date.today() + timedelta(days=days)
    await conn.execute(
        "INSERT INTO codes (code, used, expiry) VALUES ($1, FALSE, $2)",
        code, expiry
    )
    return code, expiry

async def use_code(conn, code, user_id):
    row = await conn.fetchrow("SELECT * FROM codes WHERE code = $1", code)
    if not row:
        return None, "❌ Código inválido."
    if row["used"]:
        return None, "❌ Código ya usado."
    if row["expiry"] < date.today():
        return None, "❌ Código caducado."
    await conn.execute(
        "UPDATE codes SET used = TRUE, used_by = $1 WHERE code = $2",
        user_id, code
    )
    return row["expiry"], None

def format_user(row):
    return f"{row['full_name'] or 'Sin nombre'} (@{row['username'] or 'sin @'})"

def is_admin(update: Update):
    if not update.effective_user:
        return False
    return update.effective_user.id in ADMINS

async def notify_admins(bot, message):
    for admin_id in ADMINS:
        try:
            await bot.send_message(chat_id=admin_id, text=message, parse_mode="Markdown")
        except:
            pass

# ========================
# BROADCAST (solo usuarios activos)
# ========================
async def broadcast_logic(bot, msg, broadcast_id):
    users = list(await get_users())  # Solo activos
    random.shuffle(users)
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 120

    await notify_admins(bot,
        f"🚀 *Broadcast #{broadcast_id} iniciado* ({total} usuarios activos)\n📦 Tandas de 5 cada 2 minutos"
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
        for admin_id in ADMINS:
            try:
                await bot.send_message(chat_id=admin_id,
                    text=f"📦 Broadcast #{broadcast_id} — Tanda {i // tanda_size + 1}\n\n{lista}\n\n📊 Progreso: {enviados + fallidos}/{total}"
                )
            except:
                pass

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

    if await is_user_active(user.id):
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT expiry FROM users WHERE user_id = $1", user.id)
        exp_text = row["expiry"].strftime('%d/%m/%Y') if row["expiry"] else "este mes"
        await update.message.reply_text(
            f"✅ *Ya tienes acceso activo.*\n\n📅 Tu acceso expira el *{exp_text}*",
            parse_mode="Markdown"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "🔐 *Acceso restringido.*\n\n"
            "Necesitas un código de acceso para registrarte.\n\n"
            "Usa: `/start TUCODIGO`",
            parse_mode="Markdown"
        )
        return

    code = context.args[0].upper()
    async with db_pool.acquire() as conn:
        expiry, error = await use_code(conn, code, user.id)
        if error:
            await update.message.reply_text(error)
            return
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name, expiry)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET username=$2, full_name=$3, expiry=$4
        """, user.id, user.username or "", user.full_name or "", expiry)

    await update.message.reply_text(
        f"✅ *¡Acceso concedido!*\n\n"
        f"📅 Tu acceso es válido hasta el *{expiry.strftime('%d/%m/%Y')}*\n\n"
        f"A partir de ahora recibirás los avisos directamente aquí. 🔔",
        parse_mode="Markdown"
    )
    await notify_admins(context.bot,
        f"🆕 *Nuevo usuario registrado*\n\n"
        f"👤 {user.full_name or 'Sin nombre'} (@{user.username or 'sin @'})\n"
        f"🆔 ID: `{user.id}`\n"
        f"📅 Acceso hasta: *{expiry.strftime('%d/%m/%Y')}*"
    )

async def generar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    cantidad = int(context.args[0]) if context.args else 1
    dias = int(context.args[1]) if len(context.args) > 1 else 31
    async with db_pool.acquire() as conn:
        codigos = []
        for _ in range(cantidad):
            code, expiry = await create_code(conn, days=dias)
            codigos.append(f"`{code}` — válido hasta {expiry.strftime('%d/%m/%Y')}")
    await update.message.reply_text(
        f"🎟️ *{cantidad} código(s) generado(s) por {dias} días:*\n\n" + "\n".join(codigos),
        parse_mode="Markdown"
    )

async def codigos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT code, used, used_by, expiry FROM codes ORDER BY expiry DESC")
    if not rows:
        await update.message.reply_text("No hay códigos generados.")
        return
    lines = []
    for r in rows:
        estado = f"✅ Usado por `{r['used_by']}`" if r["used"] else "🟡 Disponible"
        lines.append(f"`{r['code']}` — {estado} — caduca {r['expiry'].strftime('%d/%m/%Y')}")
    text = "🎟️ *Códigos:*\n\n" + "\n".join(lines)
    await update.message.reply_text(text[:4000], parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID: `{update.effective_chat.id}`", parse_mode="Markdown")

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    users = await get_all_users()
    activos = sum(1 for r in users if not r["expiry"] or r["expiry"] >= date.today())
    caducados = len(users) - activos
    await update.message.reply_text(
        f"👥 Total usuarios: *{len(users)}*\n✅ Activos: *{activos}*\n❌ Caducados: *{caducados}*",
        parse_mode="Markdown"
    )

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    users = await get_all_users()
    if not users:
        await update.message.reply_text("No hay usuarios registrados aún.")
        return
    lines = []
    for r in users:
        estado = "✅" if not r["expiry"] or r["expiry"] >= date.today() else "❌"
        exp = r["expiry"].strftime('%d/%m/%Y') if r["expiry"] else "abril (sin código)"
        lines.append(f"{estado} {format_user(r)} — {exp}")
    text = "👥 *Usuarios:*\n\n" + "\n".join(lines)
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
    users = await get_all_users()
    total_antes = len(users)
    await delete_all_users()
    await update.message.reply_text(
        f"🗑️ *Base de datos limpiada*\n\n"
        f"Se han eliminado *{total_antes}* usuarios.\n"
        f"El bot está listo para un nuevo mes.",
        parse_mode="Markdown"
    )

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "✉️ *Escribir cualquier mensaje* → broadcast en paralelo\n"
        "🖼️ *Foto/vídeo/documento* → también se manda a todos\n\n"
        "🎟️ *Gestión de accesos:*\n"
        "/generar N D → genera N códigos de D días (ej: `/generar 5 31`)\n"
        "/codigos → ver todos los códigos y su estado\n\n"
        "📊 *Usuarios:*\n"
        "/total → total y activos/caducados\n"
        "/lista → ver todos los usuarios con estado\n"
        "/reset → eliminar todos los usuarios\n\n"
        "📢 *Canal:*\n"
        "/anuncio → manda botón de registro al grupo\n"
        "/patrocinar → manda mensaje de patrocinio\n\n"
        "🔧 *Otros:*\n"
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
    app.add_handler(CommandHandler("generar",    generar))
    app.add_handler(CommandHandler("codigos",    codigos))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, encolar))

    print("🤖 Bot corriendo...")
    app.run_polling()