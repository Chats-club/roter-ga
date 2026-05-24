from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import pandas as pd
import re
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

FILES = {
    7: "uploads/month7.xlsx",
}

# ✅ Connect MongoDB ONCE, with error checking
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("❌ MONGO_URI environment variable is not set!")

try:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✅ MongoDB connected successfully")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    raise

db = client["flask_db"]
history_col = db["history"]


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
            day_num = bot if 'Unnamed' not in bot else ''
            new_columns.append(f"{day_name}-{day_num}")
    df.columns = new_columns
    df.columns = [re.sub(r'\.\d+$', '', str(col)) for col in df.columns]
    new_columns = df.columns.tolist()
    data = df.to_dict(orient="records")
    return render_template("month7.html", data=data, columns=new_columns)


@app.route("/month7/history", methods=["GET", "POST"])
def month7_history():
    if request.method == "POST":
        text = request.form.get("text")
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        history_col.insert_one({"time": now, "text": text})
        return redirect(url_for('month7_history'))

    data = list(history_col.find({}, {"_id": 0}))
    return render_template("month7_history.html", data=data)


# ✅ Remove month8/month9 routes if files don't exist yet
# Add them back when you have the files


if __name__ == "__main__":
    app.run(debug=True, port=5500)