"""
خادم بسيط يخلي مشروع البوت "صاحي" باستمرار على Render.
------------------------------------------------
Render (الخطة المجانية) يوقف الخدمة لو ما فيه نشاط. هذا يفتح رابط ويب بسيط،
وخدمة UptimeRobot (مجانية) تزوره كل 5 دقايق عشان يضل شغال 24 ساعة.
"""

import os
from flask import Flask
from threading import Thread

app = Flask("")


@app.route("/")
def home():
    return "البوت شغال ✅"


def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run)
    t.start()
