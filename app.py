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
    return render_template("month7.html")

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