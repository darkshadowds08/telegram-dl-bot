import os
from flask import Flask, Response, stream_with_context
import requests
import threading
from telegram import Bot

# بياناتك الخاصة وتوكن البوت
BOT_TOKEN = "9144967454:AAHhldgMw5zl_saTWG9WCCrcZdshHPpuz8Y"

flask_app = Flask(__name__)
FILE_DATABASE = {}

@flask_app.route('/')
def home():
    return "Bot is running successfully!"

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
    flask_app.run(host="0.0.0.0", port=port)
