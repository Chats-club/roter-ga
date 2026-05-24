from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import pandas as pd
import re
from pymongo import MongoClient
import os                         # 🌟 Thêm dòng này
from dotenv import load_dotenv    # 🌟 Thêm dòng này

load_dotenv()                     # 🌟 Tải các biến từ file .env lên hệ thống
app = Flask(__name__)


FILES = {
    7: "uploads/month7.xlsx"
}
#  Kết nối tới MongoDB
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)
db = client["flask_db"]          # Tên Database
history_col = db["history"]      # Tên Collection (Thay thế cho file text)
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/month7")
def month7():
    df = pd.read_excel(FILES[7],header=[0, 1])
    new_columns = []
    fixed_cols = ['E - NAME', 'ID', 'Full Name']
    
    for i, (top, bot) in enumerate(df.columns):
        top = str(top).strip()
        bot = str(bot).strip()
        
        if i < 3:  # 3 cột đầu
            new_columns.append(top if 'Unnamed' not in top else bot)
        else:
            day_name = top if 'Unnamed' not in top else ''
            day_num = bot if 'Unnamed' not in bot else ''
            new_columns.append(f"{day_name}-{day_num}")
    df.columns = new_columns
      # Bỏ số đằng sau tên cột (ví dụ: Sat.1 -> Sat, Mon.2 -> Mon)
    df.columns = [re.sub(r'\.\d+$', '', str(col)) for col in df.columns]
    data = df.to_dict(orient="records")
    columns = df.columns.tolist()
    return render_template("month7.html", data=data, columns=new_columns)

@app.route("/month7/history", methods=["GET", "POST"])
def month7_history():
    if request.method == "POST":
        text = request.form.get("text")
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        # 3. Thay vì nối chuỗi f"{now}|{text}", ta tạo một Document (Dictionary)
        new_document = {
            "time": now,
            "text": text
        }
        
        # 4. Lưu vào MongoDB bằng lệnh insert_one
        history_col.insert_one(new_document)
        # 🌟 QUAN TRỌNG: Gửi dữ liệu xong thì chuyển hướng (Redirect) về chính trang này 
        # bằng phương thức GET để tải lại toàn bộ lịch sử mới nhất.
        return redirect(url_for('month7_history'))
    # 5. Lấy toàn bộ dữ liệu từ MongoDB ra để hiển thị (Sắp xếp theo dữ liệu mới nhất lên đầu)
    # .find({}, {"_id": 0}) nghĩa là lấy hết dữ liệu và bỏ qua trường _id tự động của Mongo cho nhẹ
    data_cursor = history_col.find({}, {"_id": 0})
    data = list(data_cursor)

    return render_template("month7_history.html", data=data)

@app.route("/month8")
def month8():
    df = pd.read_excel(FILES[8])
    data = df.to_dict(orient="records")
    columns = df.columns.tolist()
    return render_template("month8.html", data=data, columns=columns)

@app.route("/month9")
def month9():
    df = pd.read_excel(FILES[9])
    data = df.to_dict(orient="records")
    columns = df.columns.tolist()
    return render_template("month9.html", data=data, columns=columns)

mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("MONGO_URI environment variable is not set!")

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

# Test connection on startup
try:
    client.admin.command('ping')
    print("✅ MongoDB connected successfully")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")

if __name__ == "__main__":
    app.run(debug=True, port=5500)