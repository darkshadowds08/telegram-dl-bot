import os
from flask import Flask, Response, stream_with_context
import requests
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# بياناتك الخاصة وتوكن البوت
API_ID = 31124352
API_HASH = "832029294d40cb38e94a3f1be77c5c59"
BOT_TOKEN = "9144967454:AAHhldgMw5zl_saTWG9WCCrcZdshHPpuz8Y"
RENDER_URL = "https://telegram-dl-bot-e4tw.onrender.com"

flask_app = Flask(__name__)
FILE_DATABASE = {}

@flask_app.route('/')
def home():
    return "Bot Server is running successfully!"

@flask_app.route('/download/<file_key>')
def download_file(file_key):
    if file_key not in FILE_DATABASE:
        return "الملف غير موجود أو انتهت صلاحيته!", 404
        
    file_data = FILE_DATABASE[file_key]
    target_url = file_data["url"]
    file_name = file_data["name"]
    file_size = file_data["size"]
    
    def generate():
        response = requests.get(target_url, stream=True)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    response = Response(stream_with_context(generate()), content_type='application/octet-stream')
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{file_name}"
    response.headers["Content-Length"] = str(file_size)
    response.headers["Accept-Ranges"] = "bytes"
    return response

# إعداد عميل تيليجرام
app = Client("telegram_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client: Client, message: Message):
    media = message.document or message.video or message.audio
    file_id = media.file_id
    file_name = getattr(media, "file_name", "downloaded_file")
    
    file_info = await client.get_media_file_path(file_id)
    telegram_direct_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info}"
    
    file_key = str(abs(hash(file_id)))
    FILE_DATABASE[file_key] = {
        "url": telegram_direct_url,
        "name": file_name,
        "size": media.file_size
    }
    
    download_link = f"{RENDER_URL}/download/{file_key}"
    
    await message.reply_text(
        f"✅ **تم الرفع بنجاح!**\n\n"
        f"📁 **اسم الملف:** `{file_name}`\n"
        f"🔗 **رابط التحميل المباشر (جاهز لـ IDM):**\n`{download_link}`",
        disable_web_page_preview=True
    )

if __name__ == "__main__":
    # تشغيل سيرفر Flask في خيط مستقل بطريقة صحيحة تمنع أي تعارض
    import threading
    port = int(os.environ.get("PORT", 5000))
    flask_thread = threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=port, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # بدء تشغيل البوت على الخيط الرئيسي
    app.run()
