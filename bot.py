import asyncio
import asyncpg
import random
import sys
import os
import secrets
from datetime import date, timedelta, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, filters, ContextTypes

# ========================
# CONFIGURACIÓN
# ========================
TOKEN = os.environ.get("TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMINS = [int(os.environ.get("ADMIN_ID"))]
GROUP_ID = int(os.environ.get("GROUP_ID"))
BOT_USERNAME = "CharmelionBot"
CANAL_LINK = "https://t.me/TU_CANAL"
DEVELOPER_ID = int(os.environ.get("DEVELOPER_ID", "0"))

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
                full_name TEXT,
                expiry DATE
            )
        """)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry DATE")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                code TEXT PRIMARY KEY,
                used BOOLEAN DEFAULT FALSE,
                used_by BIGINT,
                expiry DATE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO config (key, value) VALUES ('broadcast_counter', '0')
            ON CONFLICT (key) DO NOTHING
        """)

async def next_broadcast_id():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE config SET value = (value::int + 1)::text WHERE key = 'broadcast_counter' RETURNING value"
        )
        return int(row["value"])

async def get_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT user_id, username, full_name FROM users
            WHERE expiry IS NULL OR expiry >= $1
        """, date.today())

async def get_all_users():
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
        if not row["expiry"]:
            return True
        return row["expiry"] >= date.today()

async def register_user(user, expiry):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name, expiry)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET username=$2, full_name=$3, expiry=$4
        """, user.id, user.username or "", user.full_name or "", expiry)

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
# DETECCIÓN CAMBIO DE CANAL (para el desarrollador)
# ========================
async def mi_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    result = update.my_chat_member
    if not result or not DEVELOPER_ID:
        return
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    chat = result.chat

    if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sí, cambiar", callback_data=f"setgroup_{chat.id}"),
            InlineKeyboardButton("❌ No", callback_data="setgroup_no")
        ]])
        await context.bot.send_message(
            chat_id=DEVELOPER_ID,
            text=f"➕ *Bot añadido a un nuevo grupo*\n\n"
                 f"📛 *{chat.title}*\n🆔 `{chat.id}`\n\n"
                 f"¿Establecer como canal activo?",
            parse_mode="Markdown", reply_markup=kb
        )
    elif old_status in ("member", "administrator") and new_status in ("left", "kicked"):
        await context.bot.send_message(
            chat_id=DEVELOPER_ID,
            text=f"⚠️ *Bot eliminado de un grupo*\n\n📛 *{chat.title}*\n🆔 `{chat.id}`",
            parse_mode="Markdown"
        )

async def confirmar_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    query = update.callback_query
    await query.answer()
    if query.data == "setgroup_no":
        await query.edit_message_text("❌ Sin cambios.")
        return
    new_id = int(query.data.split("_")[1])
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO config (key, value) VALUES ('group_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            str(new_id)
        )
    GROUP_ID = new_id
    await query.edit_message_text(
        f"✅ *Canal activo actualizado*\n\n🆔 Nuevo ID: `{new_id}`",
        parse_mode="Markdown"
    )

# ========================
# AVISO AUTOMÁTICO 3 DÍAS ANTES DE EXPIRAR
# ========================
async def daily_expiry_check(bot):
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_run - now).total_seconds())

        target = date.today() + timedelta(days=3)
        async with db_pool.acquire() as conn:
            users = await conn.fetch("SELECT user_id, expiry FROM users WHERE expiry = $1", target)

        for u in users:
            try:
                await bot.send_message(
                    chat_id=u["user_id"],
                    text=f"⚠️ *Tu acceso expira en 3 días*\n\n"
                         f"📅 Fecha: *{u['expiry'].strftime('%d/%m/%Y')}*\n\n"
                         f"Contacta con el admin para renovar tu acceso.",
                    parse_mode="Markdown"
                )
            except:
                pass

# ========================
# DETECCIÓN AUTOMÁTICA DE NUEVOS MIEMBROS
# ========================
async def nuevo_miembro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result:
        return
    if result.chat.id != GROUP_ID:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.new_chat_member.user

    if user.is_bot:
        return

    if old_status in ("left", "kicked") and new_status == "member":
        expiry = date.today() + timedelta(days=31)
        await register_user(user, expiry)
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ *¡Bienvenido al VIP!*\n\n"
                     f"📅 Tu acceso es válido hasta el *{expiry.strftime('%d/%m/%Y')}*\n\n"
                     f"A partir de ahora recibirás los avisos aquí directamente. 🔔",
                parse_mode="Markdown"
            )
        except:
            pass
        await notify_admins(context.bot,
            f"🆕 *Nuevo miembro registrado*\n\n"
            f"👤 {user.full_name or 'Sin nombre'} (@{user.username or 'sin @'})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📅 Acceso hasta: *{expiry.strftime('%d/%m/%Y')}*"
        )

    elif old_status == "member" and new_status in ("left", "kicked"):
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET expiry = $1 WHERE user_id = $2",
                date.today() - timedelta(days=1), user.id
            )
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ *Has salido del canal VIP.*\n\n"
                     "Tu acceso al bot ha sido desactivado.\n"
                     "Si crees que es un error, contacta con el admin.",
                parse_mode="Markdown"
            )
        except:
            pass
        await notify_admins(context.bot,
            f"🚪 *Miembro salido/expulsado*\n\n"
            f"👤 {user.full_name or 'Sin nombre'} (@{user.username or 'sin @'})\n"
            f"🆔 ID: `{user.id}`\n"
            f"❌ Acceso desactivado"
        )

# ========================
# BROADCAST
# ========================
async def broadcast_logic(bot, msg, broadcast_id):
    users = list(await get_users())
    random.shuffle(users)
    total = len(users)
    enviados = 0
    fallidos = 0
    tanda_size = 5
    espera = 180

    await notify_admins(bot,
        f"🚀 *Broadcast #{broadcast_id} iniciado* ({total} usuarios activos)\n📦 Tandas de 5 cada 3 minutos"
    )

    for i in range(0, total, tanda_size):
        tanda = users[i:i + tanda_size]
        nombres_ok = []
        nombres_fail = []

        for row in tanda:
            try:
                uid = row["user_id"]
                if msg.photo:
                    await bot.send_photo(chat_id=uid, photo=msg.photo[-1].file_id, caption=msg.caption, protect_content=True)
                elif msg.video:
                    await bot.send_video(chat_id=uid, video=msg.video.file_id, caption=msg.caption, protect_content=True)
                elif msg.document:
                    await bot.send_document(chat_id=uid, document=msg.document.file_id, caption=msg.caption, protect_content=True)
                elif msg.audio:
                    await bot.send_audio(chat_id=uid, audio=msg.audio.file_id, caption=msg.caption, protect_content=True)
                elif msg.voice:
                    await bot.send_voice(chat_id=uid, voice=msg.voice.file_id, caption=msg.caption, protect_content=True)
                elif msg.sticker:
                    await bot.send_sticker(chat_id=uid, sticker=msg.sticker.file_id, protect_content=True)
                elif msg.animation:
                    await bot.send_animation(chat_id=uid, animation=msg.animation.file_id, caption=msg.caption, protect_content=True)
                elif msg.text:
                    await bot.send_message(chat_id=uid, text=msg.text, protect_content=True)
                enviados += 1
                nombres_ok.append(f"✅ {format_user(row)}")
            except:
                fallidos += 1
                nombres_fail.append(f"❌ {format_user(row)}")
            await asyncio.sleep(0.3)

        lista_tanda = "\n".join(nombres_ok + nombres_fail)
        for admin_id in ADMINS:
            try:
                await bot.send_message(chat_id=admin_id,
                    text=f"📦 Broadcast #{broadcast_id} — Tanda {i // tanda_size + 1}\n\n{lista_tanda}\n\n📊 Progreso: {enviados + fallidos}/{total}"
                )
            except:
                pass

        if i + tanda_size < total:
            await asyncio.sleep(espera)

    await notify_admins(bot,
        f"🏁 *Broadcast #{broadcast_id} finalizado*\n✅ Enviados: *{enviados}*\n❌ Fallidos: *{fallidos}*\n👥 Total: *{total}*"
    )

async def encolar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    bid = await next_broadcast_id()
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

    try:
        member = await context.bot.get_chat_member(GROUP_ID, user.id)
        en_grupo = member.status in ("member", "administrator", "creator")
    except Exception:
        en_grupo = False

    if en_grupo:
        expiry = date.today() + timedelta(days=31)
        await register_user(user, expiry)
        await update.message.reply_text(
            f"✅ *¡Registrado correctamente!*\n\n"
            f"📅 Tu acceso es válido hasta el *{expiry.strftime('%d/%m/%Y')}*\n\n"
            f"Recibirás los avisos aquí directamente. 🔔",
            parse_mode="Markdown"
        )
        await notify_admins(context.bot,
            f"🆕 *Nuevo registro vía /start*\n\n"
            f"👤 {user.full_name or 'Sin nombre'} (@{user.username or 'sin @'})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📅 Acceso hasta: *{expiry.strftime('%d/%m/%Y')}*"
        )
    else:
        await update.message.reply_text(
            "🔐 *Acceso restringido.*\n\n"
            "Para acceder necesitas ser miembro del canal VIP.\n\n"
            "Contacta con el admin para más información.",
            parse_mode="Markdown"
        )

async def activar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Uso: `/activar CODIGO`", parse_mode="Markdown")
        return
    code = context.args[0].upper()
    async with db_pool.acquire() as conn:
        expiry, error = await use_code(conn, code, user.id)
    if error:
        await update.message.reply_text(error)
        return
    await register_user(user, expiry)
    await update.message.reply_text(
        f"✅ *Código activado correctamente.*\n\n"
        f"📅 Tu acceso es válido hasta el *{expiry.strftime('%d/%m/%Y')}*\n\n"
        f"Recibirás los avisos aquí directamente. 🔔",
        parse_mode="Markdown"
    )
    await notify_admins(context.bot,
        f"🎟️ *Código activado*\n\n"
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

async def codigos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def extender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if len(context.args) < 2:
        await update.message.reply_text("Uso: `/extender USER_ID DIAS`", parse_mode="Markdown")
        return
    try:
        user_id = int(context.args[0])
        dias = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ USER_ID y DIAS deben ser números.")
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT expiry, full_name FROM users WHERE user_id = $1", user_id)
        if not row:
            await update.message.reply_text("❌ Usuario no encontrado.")
            return
        base = max(row["expiry"], date.today()) if row["expiry"] else date.today()
        new_expiry = base + timedelta(days=dias)
        await conn.execute("UPDATE users SET expiry = $1 WHERE user_id = $2", new_expiry, user_id)
    await update.message.reply_text(
        f"✅ *Acceso extendido*\n\n"
        f"👤 {row['full_name'] or user_id}\n"
        f"📅 Nueva expiración: *{new_expiry.strftime('%d/%m/%Y')}*",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ *Tu acceso ha sido renovado.*\n\n"
                 f"📅 Nuevo acceso hasta: *{new_expiry.strftime('%d/%m/%Y')}*",
            parse_mode="Markdown"
        )
    except:
        pass

async def expulsar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not context.args:
        await update.message.reply_text("Uso: `/expulsar USER_ID`", parse_mode="Markdown")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID debe ser un número.")
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT full_name FROM users WHERE user_id = $1", user_id)
        if not row:
            await update.message.reply_text("❌ Usuario no encontrado.")
            return
        await conn.execute(
            "UPDATE users SET expiry = $1 WHERE user_id = $2",
            date.today() - timedelta(days=1), user_id
        )
    await update.message.reply_text(
        f"✅ Usuario *{row['full_name'] or user_id}* expulsado.\n❌ Acceso desactivado.",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ *Tu acceso al bot ha sido desactivado.*\n\n"
                 "Si crees que es un error, contacta con el admin.",
            parse_mode="Markdown"
        )
    except:
        pass

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
        exp = r["expiry"].strftime('%d/%m/%Y') if r["expiry"] else "sin fecha"
        lines.append(f"{estado} {format_user(r)} — {exp}")

    chunk = "👥 *Usuarios:*\n\n"
    for line in lines:
        if len(chunk) + len(line) + 1 > 4000:
            await update.message.reply_text(chunk, parse_mode="Markdown")
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk, parse_mode="Markdown")

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
    if not context.args or context.args[0] != "CONFIRMAR":
        await update.message.reply_text(
            "⚠️ *¿Seguro que quieres borrar todos los usuarios?*\n\n"
            "Esta acción no se puede deshacer.\n\n"
            "Escribe `/reset CONFIRMAR` para ejecutarlo.",
            parse_mode="Markdown"
        )
        return
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
        "🖼️ Foto/vídeo/doc/audio/voz/sticker → también se manda a todos\n\n"
        "🎟️ *Accesos:*\n"
        "/activar CODIGO → activar acceso con código\n"
        "/generar N D → genera N códigos de D días\n"
        "/codigos → ver todos los códigos\n"
        "/extender ID DIAS → ampliar acceso de un usuario\n"
        "/expulsar ID → desactivar acceso de un usuario\n\n"
        "📊 *Usuarios:*\n"
        "/total → total y activos/caducados\n"
        "/lista → ver todos los usuarios con estado\n"
        "/reset CONFIRMAR → eliminar todos los usuarios\n\n"
        "📢 *Canal:*\n"
        "/anuncio → manda botón de registro al grupo\n"
        "/patrocinar → manda mensaje de patrocinio\n\n"
        "🔧 *Otros:*\n"
        "/id → ver el ID de un chat\n"
        "/ayuda → ver esta lista",
        parse_mode="Markdown"
    )

async def on_startup(app):
    global GROUP_ID
    await init_db()
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM config WHERE key = 'group_id'")
        if row:
            GROUP_ID = int(row["value"])
    asyncio.create_task(daily_expiry_check(app.bot))
    await notify_admins(app.bot, "🟢 *Bot iniciado correctamente*\n\nEl bot está activo y listo.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(ChatMemberHandler(nuevo_miembro, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(mi_estado,    ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(confirmar_grupo, pattern="^setgroup_"))
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("activar",     activar))
    app.add_handler(CommandHandler("id",          get_id))
    app.add_handler(CommandHandler("total",       total))
    app.add_handler(CommandHandler("lista",       lista))
    app.add_handler(CommandHandler("anuncio",     anuncio))
    app.add_handler(CommandHandler("patrocinar",  patrocinar))
    app.add_handler(CommandHandler("reset",       reset))
    app.add_handler(CommandHandler("ayuda",       ayuda))
    app.add_handler(CommandHandler("generar",     generar))
    app.add_handler(CommandHandler("codigos",     codigos_cmd))
    app.add_handler(CommandHandler("extender",    extender))
    app.add_handler(CommandHandler("expulsar",    expulsar))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, encolar))

    print("🤖 Bot corriendo...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
