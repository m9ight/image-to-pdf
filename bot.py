import asyncio
import aiosqlite
import aiofiles
import logging
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, MenuButtonWebApp, BotCommand
)
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")          # https://xxx.railway.app
ADMIN_IDS  = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]
PORT       = int(os.getenv("PORT", 8080))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = f"{WEBAPP_URL}{WEBHOOK_PATH}"

DB_PATH    = "bot.db"
WEBAPP_DIR = Path(__file__).parent / "webapp"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ===================== DATABASE =====================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_active TEXT DEFAULT (datetime('now')),
                pdfs_created INTEGER DEFAULT 0,
                images_processed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pages INTEGER NOT NULL,
                file_size INTEGER NOT NULL,
                filename TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()
    logger.info("✅ База данных инициализирована")


async def register_user(user):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_active=datetime('now')
        """, (user.id, user.username, user.first_name, user.last_name))
        await db.commit()


async def save_conversion(user_id: int, pages: int, file_size: int, filename: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO conversions (user_id, pages, file_size, filename)
            VALUES (?, ?, ?, ?)
        """, (user_id, pages, file_size, filename))
        await db.execute("""
            UPDATE users SET
                pdfs_created = pdfs_created + 1,
                images_processed = images_processed + ?,
                last_active = datetime('now')
            WHERE user_id = ?
        """, (pages, user_id))
        await db.commit()


async def get_user_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT pdfs_created, images_processed, created_at FROM users WHERE user_id = ?",
            (user_id,)
        ) as cur:
            return await cur.fetchone()


async def get_global_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM conversions") as cur:
            total_pdfs = (await cur.fetchone())[0]
        async with db.execute("SELECT SUM(pages) FROM conversions") as cur:
            row = await cur.fetchone()
            total_images = row[0] or 0
    return total_users, total_pdfs, total_images

# ===================== KEYBOARDS =====================

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Открыть конвертер",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp/"),
            icon_custom_emoji_id="6035128606563241721"
        )],
        [
            InlineKeyboardButton(
                text="Моя статистика",
                callback_data="my_stats",
                icon_custom_emoji_id="5870930636742595124"
            ),
            InlineKeyboardButton(
                text="Помощь",
                callback_data="help",
                icon_custom_emoji_id="6028435952299413210"
            )
        ]
    ])


def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="back_main"
        )],
        [InlineKeyboardButton(
            text="Открыть конвертер",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp/"),
            icon_custom_emoji_id="6035128606563241721"
        )]
    ])


def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Статистика",
            callback_data="admin_stats",
            icon_custom_emoji_id="5870921681735781843"
        )],
        [InlineKeyboardButton(
            text="◁ Назад",
            callback_data="back_main"
        )]
    ])

# ===================== BOT & DISPATCHER =====================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ===================== HANDLERS =====================

@dp.message(CommandStart())
async def start_handler(message: Message):
    await register_user(message.from_user)
    name = message.from_user.first_name or "пользователь"
    await message.answer(
        f'<b><tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Привет, {name}!</b>\n\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> Я помогу тебе конвертировать <b>изображения в PDF</b> прямо в Telegram.\n\n'
        f'<b>Что умею:</b>\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Объединять несколько фото в один PDF\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Менять порядок страниц перетаскиванием\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Настраивать размер, качество, отступы\n'
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> Поддержка JPG, PNG, WEBP, BMP, GIF\n\n'
        f'<tg-emoji emoji-id="5963103826075456248">⬆</tg-emoji> Нажми кнопку ниже, чтобы открыть конвертер:',
        reply_markup=get_main_keyboard()
    )
    try:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(
                text="Конвертер",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}/webapp/")
            )
        )
    except Exception as e:
        logger.warning(f"Не удалось установить кнопку меню: {e}")


@dp.message(Command("help"))
async def help_command(message: Message):
    await register_user(message.from_user)
    await message.answer(
        f'<b><tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji> Как пользоваться</b>\n\n'
        f'<b>1.</b> Нажми «Открыть конвертер»\n'
        f'<b>2.</b> Загрузи изображения\n'
        f'<b>3.</b> Настрой параметры PDF\n'
        f'<b>4.</b> Нажми «Конвертировать» и скачай\n\n'
        f'<b>Команды:</b>\n'
        f'/start — главное меню\n'
        f'/stats — моя статистика\n'
        f'/help — помощь',
        reply_markup=get_back_keyboard()
    )


@dp.message(Command("stats"))
async def stats_command(message: Message):
    await register_user(message.from_user)
    await show_user_stats_msg(message)


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>Нет доступа</b>')
        return
    await message.answer(
        f'<b><tg-emoji emoji-id="5870982283724328568">⚙️</tg-emoji> Панель администратора</b>',
        reply_markup=get_admin_keyboard()
    )


@dp.message(F.web_app_data)
async def web_app_data_handler(message: Message):
    import json
    await register_user(message.from_user)
    try:
        data = json.loads(message.web_app_data.data)
        if data.get("action") == "pdf_created":
            pages     = data.get("pages", 0)
            file_size = data.get("size", 0)
            filename  = data.get("filename", "document.pdf")
            await save_conversion(message.from_user.id, pages, file_size, filename)
            size_mb = file_size / 1024 / 1024
            await message.answer(
                f'<b><tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> PDF успешно создан!</b>\n\n'
                f'<tg-emoji emoji-id="5886285355279193209">🏷</tg-emoji> <b>Файл:</b> <code>{filename}</code>\n'
                f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> <b>Страниц:</b> {pages}\n'
                f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>Размер:</b> {size_mb:.2f} МБ',
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"web_app_data error: {e}")


@dp.callback_query(F.data == "my_stats")
async def my_stats_cb(callback: CallbackQuery):
    await show_user_stats_cb(callback)


@dp.callback_query(F.data == "help")
async def help_cb(callback: CallbackQuery):
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji> Как пользоваться ботом</b>\n\n'
        f'<b>1.</b> Нажми «Открыть конвертер»\n'
        f'<b>2.</b> Загрузи изображения (JPG, PNG, WEBP, BMP, GIF)\n'
        f'<b>3.</b> Настрой параметры PDF\n'
        f'<b>4.</b> Нажми «Конвертировать» и скачай файл\n\n'
        f'<b><tg-emoji emoji-id="5870982283724328568">⚙️</tg-emoji> Настройки:</b>\n'
        f'• <b>Размер</b> — A4, A3, A5, Letter или по фото\n'
        f'• <b>Ориентация</b> — авто, портрет, альбом\n'
        f'• <b>Качество</b> — 10–100%\n'
        f'• <b>Отступы</b> — поля в мм\n'
        f'• <b>Вписать</b> — масштабировать под страницу',
        reply_markup=get_back_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "back_main")
async def back_main_cb(callback: CallbackQuery):
    name = callback.from_user.first_name or "пользователь"
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> Привет, {name}!</b>\n\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> Конвертируй <b>изображения в PDF</b> прямо в Telegram.\n\n'
        f'<tg-emoji emoji-id="5963103826075456248">⬆</tg-emoji> Нажми кнопку ниже, чтобы открыть конвертер:',
        reply_markup=get_main_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    total_users, total_pdfs, total_images = await get_global_stats()
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> Глобальная статистика</b>\n\n'
        f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> <b>Пользователей:</b> {total_users:,}\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>PDF создано:</b> {total_pdfs:,}\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> <b>Изображений:</b> {total_images:,}\n\n'
        f'<tg-emoji emoji-id="5890937706803894250">📅</tg-emoji> {datetime.now().strftime("%d.%m.%Y %H:%M")}',
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


async def show_user_stats_msg(message: Message):
    row = await get_user_stats(message.from_user.id)
    if not row:
        await message.answer('<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Напишите /start сначала')
        return
    pdfs, imgs, created = row
    reg = created.split(" ")[0] if created else "—"
    await message.answer(
        f'<b><tg-emoji emoji-id="5870930636742595124">📊</tg-emoji> Ваша статистика</b>\n\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>PDF создано:</b> {pdfs}\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> <b>Изображений:</b> {imgs}\n'
        f'<tg-emoji emoji-id="5890937706803894250">📅</tg-emoji> <b>Регистрация:</b> {reg}',
        reply_markup=get_back_keyboard()
    )


async def show_user_stats_cb(callback: CallbackQuery):
    row = await get_user_stats(callback.from_user.id)
    pdfs, imgs, created = row if row else (0, 0, "—")
    reg = created.split(" ")[0] if created and created != "—" else "—"
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="5870930636742595124">📊</tg-emoji> Ваша статистика</b>\n\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>PDF создано:</b> {pdfs}\n'
        f'<tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> <b>Изображений:</b> {imgs}\n'
        f'<tg-emoji emoji-id="5890937706803894250">📅</tg-emoji> <b>Регистрация:</b> {reg}',
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

# ===================== WEB HANDLERS =====================

async def handle_webapp(request: web.Request) -> web.Response:
    html_path = WEBAPP_DIR / "index.html"
    async with aiofiles.open(html_path, "r", encoding="utf-8") as f:
        content = await f.read()
    return web.Response(text=content, content_type="text/html", charset="utf-8")


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ===================== STARTUP / SHUTDOWN =====================

async def on_startup(app: web.Application):
    await init_db()
    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="stats", description="Моя статистика"),
        BotCommand(command="help",  description="Помощь"),
    ])
    logger.info(f"✅ Webhook: {WEBHOOK_URL}")
    logger.info(f"✅ WebApp:  {WEBAPP_URL}/webapp/")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    logger.info("🛑 Webhook удалён")


# ===================== APP =====================

def create_app() -> web.Application:
    app = web.Application()

    # Telegram webhook
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Routes
    app.router.add_get("/webapp/", handle_webapp)
    app.router.add_get("/webapp",  handle_webapp)
    app.router.add_get("/health",  handle_health)
    app.router.add_get("/",        handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
