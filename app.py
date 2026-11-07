import os
from flask import Flask, Response, stream_with_context, request
import requests
import threading

# بياناتك الخاصة وتوكن البوت
BOT_TOKEN = "9144967454:AAHhldgMw5zl_saTWG9WCCrcZdshHPpuz8Y"
RENDER_URL = "https://telegram-dl-bot-e4tw.onrender.com"

flask_app = Flask(__name__)
FILE_DATABASE = {}

@flask_app.route('/')
def home():
    return "Bot Server is running successfully!"

# استقبال التحديثات من تيليجرام عبر الـ Webhook
@flask_app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    
    if update and 'message' in update:
        message = update['message']
        chat_id = message['chat']['id']
        
        # التحقق مما إذا كانت الرسالة تحتوي على ملف (مستند، فيديو، صوت، أو صورة)
        media_type = None
        file_id = None
        file_name = "downloaded_file"
        
        if 'document' in message:
            media_type = 'document'
            file_id = message['document']['file_id']
            file_name = message['document'].get('file_name', 'document')
        elif 'video' in message:
            media_type = 'video'
            file_id = message['video']['file_id']
            file_name = message['video'].get('file_name', 'video.mp4')
        elif 'audio' in message:
            media_type = 'audio'
            file_id = message['audio']['file_id']
            file_name = message['audio'].get('file_name', 'audio.mp3')
            
        if file_id:
            # الحصول على مسار الملف الحقيقي من تيليجرام
            file_path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
            res = requests.get(file_path_url).json()
            
            if res.get('ok'):
                file_path = res['result']['file_path']
                file_size = res['result'].get('file_size', 0)
                telegram_direct_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                
                # حفظ الملف في قاعدة البيانات المؤقتة
                file_key = str(abs(hash(file_id)))
                FILE_DATABASE[file_key] = {
                    "url": telegram_direct_url,
                    "name": file_name,
                    "size": file_size
                }
                
                # توليد رابط التحميل المباشر المتوافق مع IDM
                download_link = f"{RENDER_URL}/download/{file_key}"
                
                # إرسال الرد للمستخدم في تيليجرام
                reply_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": f"✅ **تم الرفع بنجاح!**\n\n📁 **اسم الملف:** `{file_name}`\n🔗 **رابط التحميل المباشر (جاهز لـ IDM):**\n`{download_link}`",
                    "parse_mode": "Markdown"
                }
                requests.post(reply_url, json=payload)
                
    return "OK", 200

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    # ربط الـ Webhook تلقائياً مع تيليجرام عند بدء التشغيل
    webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
    
    flask_app.run(host="0.0.0.0", port=port)
