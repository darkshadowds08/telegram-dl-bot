import os
import re
import json
import html
import asyncio
import hashlib
from urllib.parse import quote

import aiohttp
from aiohttp import web
from telethon import TelegramClient, events

# ====== الإعدادات (متغيرات البيئة في Render) ======
API_ID = int(os.environ["API_ID"])          # من my.telegram.org
API_HASH = os.environ["API_HASH"]           # من my.telegram.org
BOT_TOKEN = os.environ["BOT_TOKEN"]         # من @BotFather
RENDER_URL = os.environ.get("RENDER_URL", "https://telegram-dl-bot-e4tw.onrender.com").rstrip("/")
DB_FILE = os.environ.get("DB_FILE", "files_db.json")
PORT = int(os.environ.get("PORT", 5000))

CHUNK = 512 * 1024   # حجم الطلب من تيليجرام (يجب أن يقسم 1MB)
ALIGN = 4096         # تيليجرام يشترط أن يكون الـ offset من مضاعفات 4096

client = TelegramClient("bot_session", API_ID, API_HASH)

# ====== قاعدة بيانات JSON ======
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


FILE_DATABASE = load_db()


def save_db():
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(FILE_DATABASE, f, ensure_ascii=False)
    os.replace(tmp, DB_FILE)


# ====== استقبال الملفات ======
@client.on(events.NewMessage(incoming=True))
async def on_message(event):
    if not event.is_private:
        return

    if (event.raw_text or "").startswith("/start"):
        await event.reply("👋 أرسل لي أي ملف وسأعطيك رابط تحميل مباشر.\n📦 الحد الأقصى 2GB.")
        return

    msg = event.message
    if not msg.media or not msg.file:
        return

    name = msg.file.name or f"file{msg.file.ext or ''}"
    size = msg.file.size or 0

    key = hashlib.md5(f"{event.chat_id}:{msg.id}".encode()).hexdigest()[:16]
    FILE_DATABASE[key] = {
        "chat_id": event.chat_id,
        "msg_id": msg.id,
        "name": name,
        "size": size,
    }
    save_db()

    link = f"{RENDER_URL}/download/{key}"
    await event.reply(
        "✅ <b>تم الرفع بنجاح!</b>\n\n"
        f"📁 <b>اسم الملف:</b> <code>{html.escape(name)}</code>\n"
        f"📦 <b>الحجم:</b> {size / 1024 / 1024:.1f} MB\n"
        "🔗 <b>رابط التحميل المباشر (جاهز لـ IDM):</b>\n"
        f"<code>{link}</code>",
        parse_mode="html",
    )


# ====== التحميل مع دعم Range ======
def parse_range(header, size):
    """يرجع (start, end) أو None إذا غير صالح"""
    m = re.match(r"bytes=(\d*)-(\d*)$", header or "")
    if not m:
        return None
    s, e = m.groups()
    if s == "" and e == "":
        return None
    if s == "":                       # bytes=-500 (آخر 500 بايت)
        n = int(e)
        return max(size - n, 0), size - 1
    start = int(s)
    end = int(e) if e else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


async def download(request):
    key = request.match_info["key"]
    info = FILE_DATABASE.get(key)
    if not info:
        return web.Response(text="الملف غير موجود أو انتهت صلاحيته!", status=404)

    try:
        # entity=None يجلب الرسالة بالـ id مباشرة (يعمل بعد إعادة التشغيل)
        msg = await client.get_messages(None, ids=info["msg_id"])
    except Exception as e:
        print("get_messages error:", e)
        return web.Response(text="تعذر الاتصال بتيليجرام", status=502)

    if not msg or not msg.media or not msg.file:
        return web.Response(text="الملف حذف من تيليجرام", status=404)

    size = msg.file.size or info["size"]
    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(info['name'])}",
        "Accept-Ranges": "bytes",
    }

    range_header = request.headers.get("Range")
    status = 200
    start, end = 0, size - 1

    if range_header:
        rng = parse_range(range_header, size)
        if rng is None:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        start, end = rng
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    length = end - start + 1
    headers["Content-Length"] = str(length)

    resp = web.StreamResponse(status=status, headers=headers)
    await resp.prepare(request)

    aligned = (start // ALIGN) * ALIGN
    skip = start - aligned
    remaining = length

    try:
        async for chunk in client.iter_download(msg.media, offset=aligned, request_size=CHUNK):
            if skip:
                cut = min(skip, len(chunk))
                chunk = chunk[cut:]
                skip -= cut
            if not chunk:
                continue
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            await resp.write(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break
        await resp.write_eof()
    except (ConnectionResetError, asyncio.CancelledError):
        pass  # العميل أوقف التحميل
    except Exception as e:
        print("stream error:", e)
    return resp


async def home(request):
    return web.Response(text="Bot Server is running successfully!")


# ====== ping ذاتي ضد نوم Render المجاني ======
async def keep_alive():
    while True:
        await asyncio.sleep(600)
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(RENDER_URL, timeout=aiohttp.ClientTimeout(total=15))
        except Exception:
            pass


async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Telegram bot started...")

    app = web.Application()
    app.router.add_get("/", home)
    app.router.add_get("/download/{key}", download)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Web server on port {PORT}")

    asyncio.create_task(keep_alive())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
