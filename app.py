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
from google import genai

load_dotenv()
app = Flask(__name__)
from flask import send_from_directory

FILES = {
    7: "uploads/ORIGINAL7.xlsx",
}
# MANPOWERFILES = {
#     7: "uploads/month7.xlsx",
# }

# ── Gemini ────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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


# ── Roster loading helper (shared by /month7 and the Gemini endpoint) ──
def load_month7_roster():
    df = pd.read_excel(FILES[7], sheet_name='M0NTH7', header=[0, 1])
    new_columns = []
    for i, (top, bot) in enumerate(df.columns):
        top = str(top).strip()
        bot = str(bot).strip()
        if i < 2:
            new_columns.append(top if 'Unnamed' not in top else bot)
        else:
            day_name = top if 'Unnamed' not in top else ''
            day_num  = bot if 'Unnamed' not in bot else ''
            new_columns.append(f"{day_name}-{day_num}")
    df.columns = new_columns
    df.columns = [re.sub(r'\.\d+$', '', str(col)) for col in df.columns]
    return df


# ── Routes cũ ────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html", vapid_public_key=VAPID_PUBLIC_KEY)


@app.route("/month7")
def month7():
    df = load_month7_roster()
    new_columns = df.columns.tolist()
    data = df.to_dict(orient="records")
    return render_template("month7.html", data=data, columns=new_columns)


@app.route("/man_power7")
def man_power():
    df = pd.read_excel(FILES[7], sheet_name='ManPower7', header=[0, 1])

    new_columns = []
    for i, (top, bot) in enumerate(df.columns):
        top = str(top).strip()
        bot = str(bot).strip()

        if i == 0:
            new_columns.append(top if 'Unnamed' not in top else bot)
        else:
            date_val = bot if 'Unnamed' not in bot else top
            day_val  = top if 'Unnamed' not in top else ''
            new_columns.append(f"{day_val}_{date_val}" if day_val else date_val)

    df.columns = new_columns
    data = df.to_dict(orient="records")
    print("=== DATA (2 rows) ===")
    for row in data[:2]:
        print(row)
    for row in data:
        for k, v in row.items():
            if pd.isna(v) if not isinstance(v, str) else False:
                row[k] = ''

    return render_template("man_power7.html", data=data, columns=new_columns)


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


# ── Gemini: ask questions about the roster ────────
ROSTER_START_DATE = datetime(2026, 6, 26)  # roster runs 26/06/2026 → 25/07/2026


def build_dated_roster_csv(df):
    """Return CSV text where every day column header carries its real
    calendar date (DD/MM/YYYY), computed from the known roster start date.
    This removes any need for the model to infer or guess which month a
    bare day-number column (e.g. 'Fri-24') belongs to."""
    id_cols  = df.columns[:2].tolist()
    day_cols = df.columns[2:].tolist()

    dated_columns = list(id_cols)
    for i, col in enumerate(day_cols):
        actual_date = ROSTER_START_DATE + timedelta(days=i)
        dated_columns.append(f"{col} ({actual_date.strftime('%d/%m/%Y')})")

    dated_df = df.copy()
    dated_df.columns = dated_columns
    return dated_df.to_csv(index=False)


def compute_roster_stats(df):
    """Compute exact counts with pandas so Gemini doesn't have to count
    from raw text (LLMs are unreliable at counting rows/cells)."""
    id_cols  = df.columns[:2].tolist()   # e.g. staff ID + name
    day_cols = df.columns[2:].tolist()   # one column per day

    total_staff = len(df)

    shifts = df[day_cols].astype(str).apply(lambda s: s.str.strip().str.upper())

    lines = [f"Total staff on this roster: {total_staff}"]

    all_values = pd.unique(shifts.values.ravel())
    codes = sorted(v for v in all_values if v and v not in ("NAN", "NONE", ""))

    for code in codes:
        has_code = (shifts == code).any(axis=1)
        staff_count = int(has_code.sum())
        total_occurrences = int((shifts == code).sum().sum())
        lines.append(
            f"- '{code}': {staff_count} staff have at least one '{code}' shift "
            f"this month (total of {total_occurrences} '{code}' shift-days across the month)"
        )

    # ── Per-staff count cho từng shift code (tên -> số ca chính xác) ──
    name_col = id_cols[-1]  # cột cuối trong id_cols giả định là tên nhân viên
    per_staff_lines = ["\nPER-STAFF SHIFT COUNTS (exact, computed by code):"]

    for code in codes:
        code_counts = (shifts == code).sum(axis=1)
        for idx in range(total_staff):
            count = int(code_counts.iloc[idx])
            if count > 0:
                staff_name = str(df.iloc[idx][name_col])
                per_staff_lines.append(f"- {staff_name}: {count} '{code}' shift(s)")

    # ── Phân phối: bao nhiêu người có bao nhiêu ca, theo từng loại shift ──
    dist_lines = ["\nSHIFT-COUNT DISTRIBUTION (exact, computed by code):"]
    for code in codes:
        code_counts = (shifts == code).sum(axis=1)
        code_counts = code_counts[code_counts > 0]
        if code_counts.empty:
            continue
        dist_lines.append(f"'{code}' shifts:")
        value_counts = code_counts.value_counts().sort_index(ascending=False)
        for num_shifts, num_staff in value_counts.items():
            dist_lines.append(f"  - {int(num_staff)} staff have {int(num_shifts)} '{code}' shift(s)")

    # ── Nhân viên có TỔNG số ca LÀM VIỆC nhiều nhất (bỏ qua O, PH, AL) ──
    off_codes = {"O", "PH", "AL"}
    work_codes = [c for c in codes if c not in off_codes]
    work_lines = ["\nTOTAL WORKING SHIFTS PER STAFF (excludes O/PH/AL, exact, computed by code):"]
    if work_codes:
        is_work = shifts.isin(work_codes)
        work_totals = is_work.sum(axis=1)
        ranking = pd.DataFrame({
            "name": df[name_col].astype(str),
            "total_working_shifts": work_totals
        }).sort_values("total_working_shifts", ascending=False)

        max_shifts = int(ranking["total_working_shifts"].max())
        top_staff = ranking[ranking["total_working_shifts"] == max_shifts]
        top_names = ", ".join(top_staff["name"].tolist())
        work_lines.append(
            f"- Staff with the MOST total working shifts this month ({max_shifts} shifts): {top_names}"
        )
        work_lines.append("- Full ranking (highest to lowest):")
        for _, row in ranking.iterrows():
            work_lines.append(f"  - {row['name']}: {int(row['total_working_shifts'])} working shifts")

    # ── Số người ĐANG LÀM VIỆC (không phải O/PH/AL) trong TỪNG NGÀY,
    #    kèm chi tiết breakdown theo từng loại ca (A2, A8, B5, C6, D5...) ──
    off_values_for_day = {"O", "PH", "AL", "NAN", "NONE", ""}
    day_lines = ["\nDAILY WORKING HEADCOUNT + BREAKDOWN BY SHIFT CODE (exact, computed by code):"]
    for i, col in enumerate(day_cols):
        day_col_values = shifts[col]
        working_count = int((~day_col_values.isin(off_values_for_day)).sum())
        actual_date = ROSTER_START_DATE + timedelta(days=i)

        # Đếm riêng từng shift code làm việc (bỏ qua O/PH/AL) trong ngày đó
        work_codes_today = [c for c in codes if c not in off_values_for_day]
        breakdown_parts = []
        for wc in work_codes_today:
            wc_count = int((day_col_values == wc).sum())
            if wc_count > 0:
                breakdown_parts.append(f"{wc_count}{wc}")
        breakdown_str = ", ".join(breakdown_parts) if breakdown_parts else "none"

        day_lines.append(
            f"- {actual_date.strftime('%d/%m/%Y')} ({col}): {working_count} staff working total "
            f"→ {breakdown_str}"
        )


    # ── Ai lấy NHIỀU NHẤT mỗi loại ca (áp dụng cho mọi code: O, PH, AL, D5, A2, B5, C6, A8...) ──
    top_lines = ["\nTOP STAFF PER SHIFT CODE (who has the most of each code, exact, computed by code):"]
    for code in codes:
        code_counts = (shifts == code).sum(axis=1)
        max_count = int(code_counts.max())
        if max_count == 0:
            continue
        top_names = df.loc[code_counts.values == max_count, name_col].astype(str).tolist()
        top_lines.append(
            f"- '{code}': {', '.join(top_names)} — {max_count} '{code}' shift(s) each (highest in the roster)"
        )

    full_stats = "\n".join(
        lines + per_staff_lines + dist_lines + work_lines + day_lines + top_lines
    )
    return full_stats, total_staff


@app.route("/api/ask-roster", methods=["POST"])
def ask_roster():
    if not genai_client:
        return jsonify({"error": "GEMINI_API_KEY is not configured on the server"}), 500

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Missing 'question'"}), 400

    try:
        df = load_month7_roster()
    except Exception as e:
        return jsonify({"error": f"Could not load roster data: {e}"}), 500

    # CSV where every column header already carries its real calendar date —
    # no guessing required for date-based questions
    roster_csv = build_dated_roster_csv(df)

    # Exact, pre-verified statistics — Gemini must use these, not its own counting
    stats_text, total_staff = compute_roster_stats(df)

    vn_tz = timezone(timedelta(hours=7))
    today = datetime.now(vn_tz).strftime("%A, %d/%m/%Y")

    ROSTER_START = ROSTER_START_DATE.strftime("%d/%m/%Y")
    num_day_cols = len(df.columns) - 2
    ROSTER_END   = (ROSTER_START_DATE + timedelta(days=num_day_cols - 1)).strftime("%d/%m/%Y")

    prompt = f"""You are a scheduling assistant for a staff roster (GA Roster).
Today's date is {today} (Vietnam time). Shift codes: O = day off, PH = public
holiday, AL = annual leave, A2/A8/B5/C6/D5 = specific shift codes.

DATE HANDLING — READ CAREFULLY:
- This roster covers the period {ROSTER_START} to {ROSTER_END} (DD/MM/YYYY).
- Any date the user types (e.g. "24/7") is in Vietnamese DD/MM format — DAY
  comes first, then MONTH. "24/7" means the 24th of July (day=24, month=7).
- Every day column header in the CSV below already includes its exact
  calendar date in parentheses, e.g. "Fri-24 (24/07/2026)". Match the user's
  date directly against that DD/MM/YYYY value in parentheses — do not infer,
  guess, or calculate the month yourself from the day number alone.

VERIFIED STATISTICS (computed exactly with code — always trust these numbers
over anything you might calculate yourself from the raw table below):
{stats_text}

Here is the full month roster in CSV form, one row per staff member and one
column per day (each header includes its real date), for looking up
names/details (but NOT for counting totals — use the verified statistics
above for any counting question):

{roster_csv}

Answer the following question. For any question about "how many" or totals,
you MUST use the verified statistics above rather than counting cells
yourself. For date questions, match against the exact date in each column
header's parentheses — do not guess a month. Be concise and list staff names
where relevant. If the question can't be answered from this data, say so
clearly.

Question: {question}"""

    try:
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt
        )
        return jsonify({"answer": response.text})
    except Exception as e:
        return jsonify({"error": f"Gemini request failed: {e}"}), 500


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