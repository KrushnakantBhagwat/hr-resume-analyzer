from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hr_resume_secret")

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_db():
    conn = sqlite3.connect("hr_analyzer.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_database():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            phone TEXT,
            password TEXT,
            resume TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            job TEXT,
            score INTEGER,
            status TEXT,
            applied_date TEXT
        )
    """)

    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/candidate/register", methods=["GET", "POST"])
def candidate_register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        conn = get_db()
        conn.execute("""
            INSERT INTO candidates (name, email, phone, password)
            VALUES (?, ?, ?, ?)
        """, (name, email, phone, password))
        conn.commit()
        conn.close()

        return redirect("/candidate/login")

    return render_template("candidate_register.html")

@app.route("/candidate/login", methods=["GET", "POST"])
def candidate_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        candidate = conn.execute("""
            SELECT * FROM candidates
            WHERE email=? AND password=?
        """, (email, password)).fetchone()
        conn.close()

        if candidate:
            session["candidate_id"] = candidate["id"]
            return redirect("/candidate/dashboard")

        return "Invalid email or password"

    return render_template("candidate_login.html")

@app.route("/candidate/dashboard")
def candidate_dashboard():
    if "candidate_id" not in session:
        return redirect("/candidate/login")

    conn = get_db()
    candidate = conn.execute("""
        SELECT * FROM candidates WHERE id=?
    """, (session["candidate_id"],)).fetchone()

    applications = conn.execute("""
        SELECT * FROM applications WHERE candidate_id=?
    """, (session["candidate_id"],)).fetchall()
    conn.close()

    return render_template(
        "candidate_dashboard.html",
        candidate=candidate,
        applications=applications
    )

@app.route("/candidate/apply", methods=["GET", "POST"])
def apply_job():
    if "candidate_id" not in session:
        return redirect("/candidate/login")

    if request.method == "POST":
        job = request.form["job"]
        resume = request.files["resume"]

        filename = resume.filename
        if filename:
            resume.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        # Simple demonstration score
        score = 75

        conn = get_db()
        conn.execute("""
            UPDATE candidates SET resume=? WHERE id=?
        """, (filename, session["candidate_id"]))

        conn.execute("""
            INSERT INTO applications
            (candidate_id, job, score, status, applied_date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["candidate_id"],
            job,
            score,
            "Pending",
            datetime.now().strftime("%Y-%m-%d")
        ))

        conn.commit()
        conn.close()
        return redirect("/candidate/dashboard")

    return render_template("apply.html")

@app.route("/hr/login", methods=["GET", "POST"])
def hr_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "admin123":
            session["hr"] = True
            return redirect("/hr/dashboard")

        return "Invalid HR username or password"

    return render_template("hr_login.html")

@app.route("/hr/dashboard")
def hr_dashboard():
    if "hr" not in session:
        return redirect("/hr/login")

    conn = get_db()
    applications = conn.execute("""
        SELECT
            applications.id,
            candidates.name,
            candidates.email,
            candidates.phone,
            candidates.resume,
            applications.job,
            applications.score,
            applications.status,
            applications.applied_date
        FROM applications
        JOIN candidates ON applications.candidate_id = candidates.id
    """).fetchall()
    conn.close()

    return render_template("hr_dashboard.html", applications=applications)

@app.route("/hire/<int:application_id>")
def hire_candidate(application_id):
    if "hr" not in session:
        return redirect("/hr/login")

    conn = get_db()
    application = conn.execute("""
        SELECT applications.*, candidates.name, candidates.email
        FROM applications
        JOIN candidates ON applications.candidate_id = candidates.id
        WHERE applications.id=?
    """, (application_id,)).fetchone()

    conn.execute("""
        UPDATE applications SET status='Selected'
        WHERE id=?
    """, (application_id,))
    conn.commit()
    conn.close()

    if application:
        send_selection_email(application["email"], application["name"])

    return redirect("/hr/dashboard")

def send_selection_email(receiver_email, candidate_name):
    # Optional email setup:
    # sender_email = "YOUR_EMAIL@gmail.com"
    # sender_password = "YOUR_GMAIL_APP_PASSWORD"
    #
    # Do not use your normal Gmail password here.
    # Uncomment/configure the code below when email is required.

    sender_email = "YOUR_EMAIL@gmail.com"
    sender_password = "YOUR_APP_PASSWORD"

    if "YOUR_" in sender_email or "YOUR_" in sender_password:
        print("Email not configured. Candidate was marked Selected.")
        return

    try:
        message = EmailMessage()
        message["Subject"] = "Congratulations - You are Selected"
        message["From"] = sender_email
        message["To"] = receiver_email
        message.set_content(f"""
Dear {candidate_name},

Congratulations!

We are happy to inform you that you have been selected for the position.

Our HR team will contact you with further details.

Regards,
HR Department
""")

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(message)
        server.quit()

    except Exception as e:
        print("Email Error:", e)

@app.route("/resume/<filename>")
def resume(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/statistics")
def statistics():
    if "hr" not in session:
        return redirect("/hr/login")

    conn = get_db()

    total = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    selected = conn.execute("""
        SELECT COUNT(*) FROM applications WHERE status='Selected'
    """).fetchone()[0]
    pending = conn.execute("""
        SELECT COUNT(*) FROM applications WHERE status='Pending'
    """).fetchone()[0]

    month = datetime.now().strftime("%Y-%m")
    monthly_selected = conn.execute("""
        SELECT COUNT(*) FROM applications
        WHERE status='Selected' AND applied_date LIKE ?
    """, (month + "%",)).fetchone()[0]

    conn.close()

    return render_template(
        "statistics.html",
        total=total,
        selected=selected,
        pending=pending,
        monthly_selected=monthly_selected
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

create_database()

if __name__ == "__main__":
    app.run(debug=True)
