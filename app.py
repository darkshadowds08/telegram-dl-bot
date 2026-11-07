import os
import time
from flask import Flask, Response, stream_with_context
import requests
import threading

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

# دالة الاستماع للرسائل بشكل مستمر (تتجاوز مشاكل الـ Webhook كلياً)
def run_telegram_bot():
    # حذف أي Webhook قديم قد يسبب تداخلاً
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    
    offset = 0
    print("Telegram bot polling started...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            res = requests.get(url, timeout=35).json()
            
            if res.get('ok') and 'result' in res:
                for update in res['result']:
                    offset = update['update_id'] + 1
                    
                    if 'message' in update:
                        message = update['message']
                        chat_id = message['chat']['id']
                        
                        file_id = None
                        file_name = "downloaded_file"
                        
                        if 'document' in message:
                            file_id = message['document']['file_id']
                            file_name = message['document'].get('file_name', 'document')
                        elif 'video' in message:
                            file_id = message['video']['file_id']
                            file_name = message['video'].get('file_name', 'video.mp4')
                        elif 'audio' in message:
                            file_id = message['audio']['file_id']
                            file_name = message['audio'].get('file_name', 'audio.mp3')
                        elif 'photo' in message:
                            file_id = message['photo'][-1]['file_id']
                            file_name = "photo.jpg"
                            
                        if file_id:
                            file_path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
                            file_info_res = requests.get(file_path_url).json()
                            
                            if file_info_res.get('ok'):
                                file_path = file_info_res['result']['file_path']
                                file_size = file_info_res['result'].get('file_size', 0)
                                telegram_direct_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                                
                                file_key = str(abs(hash(file_id)))
                                FILE_DATABASE[file_key] = {
                                    "url": telegram_direct_url,
                                    "name": file_name,
                                    "size": file_size
                                }
                                
                                download_link = f"{RENDER_URL}/download/{file_key}"
                                
                                reply_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                                payload = {
                                    "chat_id": chat_id,
                                    "text": f"✅ **تم الرفع بنجاح!**\n\n📁 **اسم الملف:** `{file_name}`\n🔗 **رابط التحميل المباشر (جاهز لـ IDM):**\n`{download_link}`",
                                    "parse_mode": "Markdown"
                                }
                                requests.post(reply_url, json=payload)
                                
        except Exception as e:
            print("Polling error:", str(e))
            time.sleep(3)

if __name__ == "__main__":
    # تشغيل بوت تيليجرام في خلفية السيرفر
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # تشغيل سيرفر الفلاسك
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
