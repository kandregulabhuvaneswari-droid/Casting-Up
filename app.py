from datetime import datetime
from pathlib import Path
import sqlite3
import os

from flask import Flask, render_template, request, redirect, url_for, session
from sqlite3 import IntegrityError

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")

# Admin authentication key from environment variable
ADMIN_KEY = os.environ.get("ADMIN_KEY", "admin123")

db_path = Path(__file__).parent / "applicants.db"


def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def reorganize_ids():
    """Reorganize IDs to be sequential after deletion"""
    conn = get_db_connection()
    try:
        # Get all applicants ordered by created_at
        applicants = conn.execute(
            "SELECT * FROM applicants ORDER BY created_at ASC"
        ).fetchall()
        
        # Delete all rows
        conn.execute("DELETE FROM applicants")
        
        # Re-insert with new sequential IDs
        for idx, app in enumerate(applicants, 1):
            conn.execute(
                "INSERT INTO applicants (id, full_name, age, email, phone, experience, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (idx, app['full_name'], app['age'], app['email'], app['phone'], app['experience'], app['created_at'], app['status'])
            )
        
        conn.commit()
    except Exception as e:
        print(f"Error reorganizing IDs: {e}")
    finally:
        conn.close()


def init_db():
    try:
        conn = get_db_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applicants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                experience TEXT,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
            """
        )
        
        # Add status column if it doesn't exist
        try:
            conn.execute("ALTER TABLE applicants ADD COLUMN status TEXT DEFAULT 'pending'")
        except:
            pass  # Column already exists
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"ERROR initializing database: {e}")
        raise


@app.before_request
def setup_database():
    if not hasattr(app, "db_initialized"):
        init_db()
        app.db_initialized = True


@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception as e:
        print(f"ERROR in home route: {e}")
        return f"Error: {str(e)}", 500

@app.route("/health")
def health():
    return "OK", 200


@app.route("/audition")
def audition():
    return render_template("audition.html")


@app.route("/apply", methods=["GET", "POST"])
def apply():
    errors = []
    form_data = {
        "full_name": "",
        "age": "",
        "email": "",
        "phone": "",
        "experience": "",
    }

    if request.method == "POST":
        form_data["full_name"] = request.form.get("full_name", "").strip()      
        form_data["age"] = request.form.get("age", "").strip()
        form_data["email"] = request.form.get("email", "").strip().lower()      
        form_data["phone"] = request.form.get("phone", "").strip()
        form_data["experience"] = request.form.get("experience", "").strip()    

        if not form_data["full_name"]:
            errors.append("Full Name is required.")
        if not form_data["age"] or not form_data["age"].isdigit():
            errors.append("Valid age is required.")
        if not form_data["email"]:
            errors.append("Email is required.")
        if not form_data["phone"]:
            errors.append("Phone number is required.")

        if not errors:
            try:
                conn = get_db_connection()
                conn.execute(
                    "INSERT INTO applicants (full_name, age, email, phone, experience, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        form_data["full_name"],
                        int(form_data["age"]),
                        form_data["email"],
                        form_data["phone"],
                        form_data["experience"],
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
                conn.close()
                return redirect(url_for("success"))
            except IntegrityError:
                errors.append("An application with this email already exists.") 
            except Exception:
                errors.append("Unable to save your application. Please try again.")

    return render_template("apply.html", errors=errors, form=form_data)


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        key = request.form.get("key", "").strip()
        if key == ADMIN_KEY:
            session["admin_authenticated"] = True
            return redirect(url_for("admin"))
        else:
            error = "Invalid authentication key. Please try again."
    
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("home"))


@app.route("/admin")
def admin():
    # Check if user is authenticated
    if not session.get("admin_authenticated"):
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    applicants = conn.execute(
        "SELECT id, full_name, age, email, phone, experience, created_at, status FROM applicants ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return render_template("admin.html", applicants=applicants)


@app.route("/admin/accept/<int:applicant_id>", methods=["POST"])
def accept_applicant(applicant_id):
    # Check if user is authenticated
    if not session.get("admin_authenticated"):
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    conn.execute("UPDATE applicants SET status = ? WHERE id = ?", ("accepted", applicant_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/reject/<int:applicant_id>", methods=["POST"])
def reject_applicant(applicant_id):
    # Check if user is authenticated
    if not session.get("admin_authenticated"):
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    conn.execute("UPDATE applicants SET status = ? WHERE id = ?", ("rejected", applicant_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404

@app.errorhandler(500)
def server_error(error):
    print(f"ERROR 500: {error}")
    return f"Server error: {str(error)}", 500


# Initialize database on startup
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)