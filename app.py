from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timezone, timedelta
import pandas as pd
import re
from pymongo import MongoClient
from pywebpush import webpush, WebPushException
import os
import json
from dotenv import load_dotenv
import certifi

load_dotenv()
app = Flask(__name__)
from flask import send_from_directory

FILES = {
    7: "uploads/month7.xlsx",
}

# ── MongoDB ───────────────────────────────────────
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("❌ MONGO_URI environment variable is not set!")

try:
    client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000,
        tlsCAFile=certifi.where()
    )
    client.admin.command('ping')
    print("✅ MongoDB connected successfully")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    raise

db               = client["flask_db"]
history_col      = db["history"]
subscriptions_col = db["push_subscriptions"]  # ← collection mới

# ── VAPID Keys (thêm vào .env) ────────────────────
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL       = os.getenv("VAPID_EMAIL", "mailto:admin@example.com")


# ── Routes cũ ────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/month7")
def month7():
    df = pd.read_excel(FILES[7], header=[0, 1])
    new_columns = []
    for i, (top, bot) in enumerate(df.columns):
        top = str(top).strip()
        bot = str(bot).strip()
        if i < 3:
            new_columns.append(top if 'Unnamed' not in top else bot)
        else:
            day_name = top if 'Unnamed' not in top else ''
            day_num  = bot if 'Unnamed' not in bot else ''
            new_columns.append(f"{day_name}-{day_num}")
    df.columns = new_columns
    df.columns = [re.sub(r'\.\d+$', '', str(col)) for col in df.columns]
    new_columns = df.columns.tolist()
    data = df.to_dict(orient="records")
    return render_template("month7.html", data=data, columns=new_columns,
                           vapid_public_key=VAPID_PUBLIC_KEY)  # ← truyền key


@app.route("/month7/history", methods=["GET", "POST"])
def month7_history():
    if request.method == "POST":
        text   = request.form.get("text")
        vn_tz  = timezone(timedelta(hours=7))
        now    = datetime.now(vn_tz).strftime("%d/%m/%Y %H:%M")
        history_col.insert_one({"time": now, "text": text})
        return redirect(url_for('month7_history'))
    data = list(history_col.find({}, {"_id": 0}))
    return render_template("month7_history.html", data=data)


# ── Push Notification Routes ──────────────────────
@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    sub = request.get_json()
    subscriptions_col.update_one(
        {"endpoint": sub["endpoint"]},
        {"$set": sub},
        upsert=True
    )
    return jsonify({"status": "ok"})


def send_push_to_all(title, body):
    subs   = list(subscriptions_col.find())
    failed = []
    count  = 0

    for sub in subs:
        sub.pop("_id")
        try:
            webpush(
    subscription_info=sub,
    data=json.dumps({
        "title": title,
        "body": body
    }),
    vapid_private_key=VAPID_PRIVATE_KEY,
    vapid_claims={
        "sub": VAPID_EMAIL
    }
)
            count += 1
        except WebPushException as e:
            print(f"Push failed: {e}")
            if "410" in str(e) or "404" in str(e):
                failed.append(sub["endpoint"])

    if failed:
        subscriptions_col.delete_many({"endpoint": {"$in": failed}})

    return count

@app.route("/admin/notify", methods=["GET", "POST"])
def admin_notify():
    if request.method == "POST":
        title = request.form.get("title", "Roster Update")
        body  = request.form.get("body", "")
        sent  = send_push_to_all(title, body)
        total = subscriptions_col.count_documents({})
        return render_template("admin_notify.html",
                               success=True, sent=sent, total=total)

    total = subscriptions_col.count_documents({})
    return render_template("admin_notify.html", total=total)

@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory("static", "service-worker.js",
                                   mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response
@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json",
                               mimetype="application/manifest+json")
if __name__ == "__main__":
    app.run(debug=True, port=5500)