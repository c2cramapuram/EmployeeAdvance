from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from supabase import create_client, Client
import os

app = Flask(__name__, template_folder="Templates")
app.secret_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpqb2NiaHppdm54YXNseW1rYnF4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk4MjI4MzQsImV4cCI6MjA3NTM5ODgzNH0.rxZ2kDUlpzbRWmoHy5ZV8atp-Uwou95wvHCu0rotjWM"

# ---------- SUPABASE CONFIG ----------
SUPABASE_URL = "https://zjocbhzivnxaslymkbqx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpqb2NiaHppdm54YXNseW1rYnF4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTgyMjgzNCwiZXhwIjoyMDc1Mzk4ODM0fQ.23c4MtUbiHg79UDvLg785H2iqbXQkWBBBv689WJKmjU"  # Use service role key from Supabase → Settings → API
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- ROUTES ----------

@app.route("/employees", methods=["GET", "POST"])
def manage_employees():
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    # Add new employee
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        try:
            supabase.table("users").insert({
                "username": username,
                "password_hash": generate_password_hash(password),
                "role": "employee"
            }).execute()
        except Exception as e:
            print("Error adding employee:", e)

    # Fetch all employees
    employees = supabase.table("users").select("id, username").eq("role", "employee").execute().data
    return render_template("employees.html", employees=employees)

@app.route("/delete_employee/<int:user_id>")
def delete_employee(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    supabase.table("users").delete().eq("id", user_id).execute()
    return redirect(url_for("manage_employees"))

@app.route("/reset_password/<int:user_id>", methods=["GET", "POST"])
def reset_password(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    row = supabase.table("users").select("username").eq("id", user_id).eq("role", "employee").execute().data
    if not row:
        return "Employee not found"
    username = row[0]["username"]

    if request.method == "POST":
        new_password = request.form["new_password"]
        supabase.table("users").update({
            "password_hash": generate_password_hash(new_password)
        }).eq("id", user_id).execute()
        return redirect(url_for("manage_employees"))

    return render_template("reset_password.html", username=username)

@app.route("/history/<employee>")
def history(employee):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "employee" and employee != session["username"]:
        return "Not allowed", 403

    # Fetch transactions from Supabase
    supabase_rows = supabase.table("transactions")\
        .select("type, amount, comment, created_at")\
        .eq("employee", employee)\
        .order("created_at", desc=True)\
        .execute().data

    # Convert UTC ISO strings to IST for display
    rows = []
    for r in supabase_rows:
        created_at_str = ""
        if r.get("created_at"):
            utc_time = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            ist_time = utc_time + timedelta(hours=5, minutes=30)
            created_at_str = ist_time.strftime("%Y-%m-%d %H:%M:%S")
        rows.append({
            "type": r["type"],
            "amount": r["amount"],
            "comment": r.get("comment", ""),
            "created_at": created_at_str
        })

    return render_template("history.html", employee=employee, rows=rows)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        row = supabase.table("users").select("id, password_hash, role").eq("username", username).execute().data
        if row and check_password_hash(row[0]["password_hash"], password):
            session["user_id"] = row[0]["id"]
            session["username"] = username
            session["role"] = row[0]["role"]
            return redirect(url_for("index"))
        else:
            return "Invalid username or password"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "employee":
        rows = supabase.table("transactions").select("employee, type, amount").eq("employee", session["username"]).execute().data
    else:
        rows = supabase.table("transactions").select("employee, type, amount").execute().data

    # Calculate totals
    balances = {}
    for r in rows:
        emp = r["employee"]
        ttype = r["type"]
        amt = r["amount"]
        if emp not in balances:
            balances[emp] = {"total_advance": 0, "total_salary": 0}
        if ttype == "advance":
            balances[emp]["total_advance"] += amt
        elif ttype == "salary":
            balances[emp]["total_salary"] += amt

    # Convert to list for template
    balances_list = []
    for emp, val in balances.items():
        balances_list.append({
            "employee": emp,
            "total_advance": val["total_advance"],
            "total_salary": val["total_salary"],
            "balance": val["total_salary"] - val["total_advance"]
        })

    return render_template("index.html", balances=balances_list, username=session["username"], role=session["role"])

@app.route("/add", methods=["GET", "POST"])
def add_transaction():
    if "user_id" not in session:
        return redirect(url_for("login"))

    allowed_types = ["advance"]
    if session["role"] == "admin":
        allowed_types.append("salary")

    # Fetch employees for admin dropdown
    employees = []
    if session["role"] == "admin":
        emp_rows = supabase.table("users").select("username").eq("role", "employee").execute().data
        employees = [{'username': e["username"]} for e in emp_rows]

    if request.method == "POST":
        if session["role"] == "employee":
            employee = session["username"]
        else:
            employee = request.form["employee"]

        ttype = request.form["type"]
        amount = float(request.form["amount"])
        comment = request.form.get("comment", "")

        if ttype not in allowed_types:
            return "Not allowed", 403

        # Insert transaction via Supabase
        supabase.table("transactions").insert({
            "employee": employee,
            "type": ttype,
            "amount": amount,
            "comment": comment
        }).execute()

        return redirect(url_for("index"))

    return render_template("add.html", role=session["role"], username=session["username"], employees=employees)

# ---------- CREATE DEFAULT ADMIN ----------
def create_default_admin():
    row = supabase.table("users").select("*").eq("username", "admin").execute().data
    if not row:
        supabase.table("users").insert({
            "username": "admin",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin"
        }).execute()

if __name__ == "__main__":
    create_default_admin()
    app.run(debug=True)
