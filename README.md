# 🦎 CharmelionBot — Bot de gestión de canales VIP en Telegram

Bot de Telegram para **gestionar suscripciones, miembros y difusión de mensajes** en
canales/grupos VIP de pago. Pensado para desplegarse **uno por cliente**: cuando el
cliente lo añade como administrador a su grupo, el bot se autoconfigura detectando
el grupo y el administrador, y a partir de ahí todo se maneja con menús de botones.

Forma parte del ecosistema de mi [plataforma SaaS de bots](https://github.com/AdriDz/saas-bots)
(es la plantilla que el orquestador clona y despliega por cada venta), pero funciona
también de forma independiente.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-22-26A5E4?logo=telegram&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-asyncpg-4169E1?logo=postgresql&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)

---

## ✨ Funcionalidades

- **Gestión de suscripciones**: alta de usuarios con fecha de caducidad y comprobación
  diaria de vencimientos.
- **Control de acceso al canal VIP**: detecta altas y bajas de miembros y avisa al admin.
- **Difusión masiva (broadcast)** a todos los usuarios:
  - Envío **por tandas** para respetar los límites de la API de Telegram.
  - **Cancelable en mitad del envío** desde un botón.
  - IDs de difusión incrementales para llevar el control.
- **Panel de administración por botones** (inline keyboards): todo se opera sin recordar
  comandos; solo difundir requiere escribir el mensaje directamente.
- **Autoconfiguración**: al añadirlo como admin a un grupo, detecta y fija el `GROUP_ID`
  y el `ADMIN_ID` automáticamente.
- **Autogestión en Railway**: el propio bot puede actualizar sus variables de entorno y
  reiniciarse vía la API GraphQL de Railway.

---

## 🛠️ Stack técnico

| Capa | Tecnología |
|------|------------|
| Lenguaje | Python 3 (asyncio) |
| Framework bot | `python-telegram-bot` |
| Base de datos | PostgreSQL con `asyncpg` (pool de conexiones) |
| HTTP | `aiohttp` |
| Infraestructura | Railway (Nixpacks) |

---

## 🧩 Decisiones de diseño interesantes

- **Difusión robusta**: se guarda una referencia fuerte a la `task` de difusión para
  evitar que el *garbage collector* de Python mate la tarea durante las esperas entre
  tandas (un bug real que se daba al quedarse "colgado" en la tanda 1).
- **Espera cancelable**: las pausas entre tandas usan un mecanismo de espera que se puede
  interrumpir, de modo que el admin puede parar una difusión en curso al instante.
- **Pool de conexiones** a PostgreSQL reutilizado en toda la app en lugar de abrir/cerrar
  conexión por consulta.

---

## ⚙️ Variables de entorno

```bash
TOKEN                # token del bot (BotFather)
DATABASE_URL         # cadena de conexión PostgreSQL
GROUP_ID             # id del grupo VIP (se autodetecta al añadirlo como admin)
ADMIN_ID             # id del administrador/cliente
DEVELOPER_ID         # id del desarrollador (avisos técnicos)

# Autogestión en Railway (opcional)
RAILWAY_TOKEN
RAILWAY_PROJECT_ID
RAILWAY_SERVICE_ID
RAILWAY_ENV_ID
```

> ⚠️ Nunca se commitea ningún token ni la base de datos: `.env` y `*.db` están en
> `.gitignore`.

---

## 🚀 Ejecutar en local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export TOKEN="123456:ABC..."
export DATABASE_URL="postgresql://usuario:pass@localhost:5432/charmelion"

python bot.py
```

En producción se despliega en Railway con `startCommand = "python bot.py"`
(ver `railway.toml`).

---

## 👤 Autor

**Adrián Díaz-Rullo Redondo** — Desarrollador Multiplataforma
[github.com/AdriDz](https://github.com/AdriDz)
