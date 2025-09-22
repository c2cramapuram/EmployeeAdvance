from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

#app = Flask(__name__)
app = Flask(__name__, template_folder="Templates")
app.secret_key = "supersecretkey"

# ---------- DATABASE INIT ----------
def init_db():
    conn = sqlite3.connect("salary.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee TEXT,
        type TEXT,
        amount REAL,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT
    )
    """)
    conn.commit()
    conn.close()

def clear_transactions():
    conn = sqlite3.connect("salary.db")
    c = conn.cursor()
    c.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
    print("✅ All transactions have been deleted.")
# ---------- ROUTES ----------

@app.route("/employees", methods=["GET", "POST"])
def manage_employees():
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    conn = sqlite3.connect("salary.db")
    c = conn.cursor()

    # Add new employee
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        try:
            from werkzeug.security import generate_password_hash
            c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                      (username, generate_password_hash(password), "employee"))
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # username already exists

    # Fetch all employees
    c.execute("SELECT id, username FROM users WHERE role='employee'")
    employees = c.fetchall()
    conn.close()

    return render_template("employees.html", employees=employees)

@app.route("/delete_employee/<int:user_id>")
def delete_employee(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    conn = sqlite3.connect("salary.db")
    c = conn.cursor()
    # Delete user
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("manage_employees"))

@app.route("/reset_password/<int:user_id>", methods=["GET", "POST"])
def reset_password(user_id):
    if "user_id" not in session or session["role"] != "admin":
        return "Not allowed", 403

    conn = sqlite3.connect("salary.db")
    c = conn.cursor()

    # Fetch employee info
    c.execute("SELECT username FROM users WHERE id=? AND role='employee'", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return "Employee not found"

    username = row[0]

    if request.method == "POST":
        new_password = request.form["new_password"]
        c.execute("UPDATE users SET password_hash=? WHERE id=?",
                  (generate_password_hash(new_password), user_id))
        conn.commit()
        conn.close()
        return redirect(url_for("manage_employees"))

    conn.close()
    return render_template("reset_password.html", username=username)


from werkzeug.security import generate_password_hash, check_password_hash
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        current = request.form["current_password"]
        new = request.form["new_password"]
        confirm = request.form["confirm_password"]

        if new != confirm:
            return "New passwords do not match"

        conn = sqlite3.connect("salary.db")
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE id=?", (session["user_id"],))
        row = c.fetchone()

        if not row or not check_password_hash(row[0], current):
            conn.close()
            return "Current password is incorrect"

        # Update password
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), session["user_id"]))
        conn.commit()
        conn.close()

        return "Password changed successfully. <a href='/'>Go back</a>"

    return render_template("change_password.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = sqlite3.connect("salary.db")
        c = conn.cursor()
        c.execute("SELECT id, password_hash, role FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()

        if row and check_password_hash(row[1], password):
            session["user_id"] = row[0]
            session["username"] = username
            session["role"] = row[2]
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

    conn = sqlite3.connect("salary.db")
    c = conn.cursor()

    if session["role"] == "employee":
        c.execute("""
        SELECT employee,
               SUM(CASE WHEN type='advance' THEN amount ELSE 0 END),
               SUM(CASE WHEN type='salary' THEN amount ELSE 0 END)
        FROM transactions
        WHERE employee=?
        GROUP BY employee
        """, (session["username"],))
    else:
        c.execute("""
        SELECT employee,
               SUM(CASE WHEN type='advance' THEN amount ELSE 0 END),
               SUM(CASE WHEN type='salary' THEN amount ELSE 0 END)
        FROM transactions
        GROUP BY employee
        """)

    rows = c.fetchall()
    conn.close()

    balances = []
    for r in rows:
        emp, adv, sal = r
        adv = adv or 0
        sal = sal or 0
        balances.append({
            "employee": emp,
            "total_advance": adv,
            "total_salary": sal,
            "balance": sal - adv
        })

    return render_template("index.html", balances=balances, username=session["username"], role=session["role"])


@app.route("/add", methods=["GET", "POST"])
def add_transaction():
    if "user_id" not in session:
        return redirect(url_for("login"))

    allowed_types = ["advance"]
    if session["role"] == "admin":
        allowed_types.append("salary")

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

        conn = sqlite3.connect("salary.db")
        c = conn.cursor()
        c.execute("INSERT INTO transactions (employee, type, amount, comment) VALUES (?, ?, ?, ?)",
                  (employee, ttype, amount, comment))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    return render_template("add.html", role=session["role"], username=session["username"])


from datetime import datetime, timedelta

@app.route("/history/<employee>")
def history(employee):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "employee" and employee != session["username"]:
        return "Not allowed", 403

    conn = sqlite3.connect("salary.db")
    c = conn.cursor()
    c.execute("SELECT type, amount, comment, created_at FROM transactions WHERE employee=? ORDER BY created_at DESC", (employee,))
    rows = c.fetchall()
    conn.close()

    # Convert UTC to IST
    ist_rows = []
    for ttype, amount, comment, created_at in rows:
        if created_at:
            utc_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            ist_time = utc_time + timedelta(hours=5, minutes=30)
            created_at_str = ist_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_at_str = ""
        ist_rows.append((ttype, amount, comment, created_at_str))

    return render_template("history.html", employee=employee, rows=ist_rows)


# ---------- CREATE DEFAULT ADMIN ----------
def create_default_admin():
    conn = sqlite3.connect("salary.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                  ("admin", generate_password_hash("admin123"), "admin"))
        conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    create_default_admin()
    app.run(debug=True)
