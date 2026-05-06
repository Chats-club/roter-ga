from flask import Flask, render_template,redirect,request
from datetime import datetime
import pandas as pd
import re

app = Flask(__name__)

# Đường dẫn file Excel trực tiếp
FILES = {
    7: "uploads/Bảng tính không có tiêu đề-3.xlsx",
    8: "uploads/Tài Liệu 08.xlsx",  # đổi tên file đúng
    9: "uploads/Tài Liệu 09.xlsx",  # đổi tên file đúng
}

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/month7")
def month7():
    df = pd.read_excel(FILES[7],header=[0, 1])
    new_columns = []
    fixed_cols = ['E - NAME', 'NO.', 'ID', 'Full Name']
    
    for i, (top, bot) in enumerate(df.columns):
        top = str(top).strip()
        bot = str(bot).strip()
        
        if i < 4:  # 4 cột đầu
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

        # ✅ phải có dấu |
        line = f"{now}|{text}"

        with open("history_month7.txt", "a") as f:
            f.write(line + "\n")

    with open("history_month7.txt", "r") as f:
        data = f.readlines()

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

if __name__ == "__main__":
    app.run(debug=True, port=5500)