from flask import Flask, jsonify,request
from flask_cors import CORS
import sqlite3
import os
from ai_engine import analyze_report

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "barrierai.db")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():

    connection = get_db_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # USERS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------------
    # REPORTS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT NOT NULL,
            barrier_type TEXT NOT NULL,
            description TEXT,
            location TEXT,
            latitude REAL,
            longitude REAL,
            image_path TEXT,
            severity TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'reported',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # DETECTIONS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT NOT NULL,
            barrier_type TEXT NOT NULL,
            confidence REAL,
            description TEXT,
            location TEXT,
            latitude REAL,
            longitude REAL,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # --------------------------------------------------------
    # SETTINGS TABLE
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            notifications INTEGER DEFAULT 1,
            dark_mode INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    connection.close()


# ============================================================
# TEST ROUTE
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "status": "success",
        "message": "BarrierAI Flask server is running",
        "database": "SQLite connected"
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health")
def health_check():

    return jsonify({
        "status": "ok",
        "server": "Flask",
        "database": "SQLite"
    })

# ============================================================
# AUTHENTICATION - REGISTER
# ============================================================

from werkzeug.security import generate_password_hash, check_password_hash


@app.route("/api/register", methods=["POST"])
def register():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "message": "No data received"
        }), 400

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not name or not email or not password:
        return jsonify({
            "status": "error",
            "message": "Name, email and password are required"
        }), 400

    if len(password) < 6:
        return jsonify({
            "status": "error",
            "message": "Password must contain at least 6 characters"
        }), 400

    connection = get_db_connection()

    try:

        existing_user = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            return jsonify({
                "status": "error",
                "message": "An account with this email already exists"
            }), 409

        password_hash = generate_password_hash(password)

        cursor = connection.execute(
            """
            INSERT INTO users
            (name, email, password)
            VALUES (?, ?, ?)
            """,
            (name, email, password_hash)
        )

        user_id = cursor.lastrowid

        connection.execute(
            """
            INSERT INTO settings
            (user_id, notifications, dark_mode)
            VALUES (?, 1, 0)
            """,
            (user_id,)
        )

        connection.commit()

        return jsonify({
            "status": "success",
            "message": "Account created successfully",
            "user": {
                "id": user_id,
                "name": name,
                "email": email
            }
        }), 201

    except sqlite3.IntegrityError:

        connection.rollback()

        return jsonify({
            "status": "error",
            "message": "Email is already registered"
        }), 409

    except Exception as error:

        connection.rollback()

        return jsonify({
            "status": "error",
            "message": "Unable to create account",
            "details": str(error)
        }), 500

    finally:

        connection.close()


# ============================================================
# AUTHENTICATION - LOGIN
# ============================================================

@app.route("/api/login", methods=["POST"])
def login():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "message": "No data received"
        }), 400

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({
            "status": "error",
            "message": "Email and password are required"
        }), 400

    connection = get_db_connection()

    try:

        user = connection.execute(
            """
            SELECT id, name, email, password, created_at
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if user is None:
            return jsonify({
                "status": "error",
                "message": "Invalid email or password"
            }), 401

        password_valid = check_password_hash(
            user["password"],
            password
        )

        if not password_valid:
            return jsonify({
                "status": "error",
                "message": "Invalid email or password"
            }), 401

        return jsonify({
            "status": "success",
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "created_at": user["created_at"]
            }
        }), 200

    except Exception as error:

        return jsonify({
            "status": "error",
            "message": "Unable to login",
            "details": str(error)
        }), 500

    finally:

        connection.close()

# ============================================================
# PART 4 - BARRIER REPORT API
# ============================================================

@app.route("/api/reports", methods=["POST"])
def create_report():

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "No report data received"
            }), 400

        category = data.get("category", "").strip()
        barrier_type = data.get("barrier_type", "").strip()
        description = data.get("description", "").strip()
        severity = data.get("severity", "medium").strip()
        location = data.get(
            "location",
            "Location not provided"
        ).strip()

        latitude = data.get("latitude")
        longitude = data.get("longitude")

        image_path = data.get("image")

        user_id = data.get("user_id")

        if not category:
            return jsonify({
                "success": False,
                "message": "Category is required"
            }), 400

        if not barrier_type:
            return jsonify({
                "success": False,
                "message": "Barrier type is required"
            }), 400

        if not description:
            return jsonify({
                "success": False,
                "message": "Description is required"
            }), 400

        connection = get_db_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO reports (
                user_id,
                category,
                barrier_type,
                description,
                location,
                latitude,
                longitude,
                image_path,
                severity,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                category,
                barrier_type,
                description,
                location,
                latitude,
                longitude,
                image_path,
                severity,
                "reported"
            )
        )

        report_id = cursor.lastrowid

        connection.commit()

        connection.close()

        return jsonify({
            "success": True,
            "message": "Report submitted successfully",
            "report_id": report_id
        }), 201

    except Exception as error:

        print(
            "REPORT ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": str(error)
        }), 500
      


# ============================================================
# GET ALL REPORTS
# ============================================================

@app.route("/api/reports", methods=["GET"])
def get_reports():

    try:

        connection = get_db_connection()

        rows = connection.execute("""
            SELECT
                id,
                user_id,
                category,
                barrier_type,
                description,
                location,
                latitude,
                longitude,
                image_path,
                severity,
                status,
                created_at
            FROM reports
            ORDER BY id DESC
        """).fetchall()

        connection.close()

        reports = []

        for row in rows:

            reports.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "category": row["category"],
                "barrier_type": row["barrier_type"],
                "description": row["description"],
                "location": row["location"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "image": row["image_path"],
                "severity": row["severity"],
                "status": row["status"],
                "created_at": row["created_at"]
            })

        return jsonify({
            "success": True,
            "reports": reports,
            "count": len(reports)
        }), 200

    except Exception as error:

        print(
            "GET REPORTS ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Failed to load reports",
            "error": str(error)
        }), 500


@app.route("/api/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):

    try:

        connection = get_db_connection()

        row = connection.execute("""
            SELECT
                id,
                user_id,
                category,
                barrier_type,
                description,
                location,
                latitude,
                longitude,
                image_path,
                severity,
                status,
                created_at
            FROM reports
            WHERE id = ?
        """, (report_id,)).fetchone()

        connection.close()

        if row is None:

            return jsonify({
                "success": False,
                "message": "Report not found"
            }), 404

        report = {
            "id": row["id"],
            "user_id": row["user_id"],
            "category": row["category"],
            "barrier_type": row["barrier_type"],
            "description": row["description"],
            "location": row["location"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "image": row["image_path"],
            "severity": row["severity"],
            "status": row["status"],
            "created_at": row["created_at"]
        }

        return jsonify({
            "success": True,
            "report": report
        }), 200

    except Exception as error:

        print(
            "GET REPORT ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Failed to load report",
            "error": str(error)
        }), 500

@app.route("/api/reports/<int:report_id>/status", methods=["PUT"])
def update_report_status(report_id):

    try:

        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "success": False,
                "message": "No status data received"
            }), 400

        status = str(
            data.get("status", "")
        ).strip().lower()

        allowed_statuses = [
            "reported",
            "under_review",
            "resolved"
        ]

        if status not in allowed_statuses:

            return jsonify({
                "success": False,
                "message": "Invalid status",
                "allowed_statuses": allowed_statuses
            }), 400

        connection = get_db_connection()

        cursor = connection.execute(
            """
            UPDATE reports
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                report_id
            )
        )

        connection.commit()

        if cursor.rowcount == 0:

            connection.close()

            return jsonify({
                "success": False,
                "message": "Report not found"
            }), 404

        connection.close()

        return jsonify({
            "success": True,
            "message": "Report status updated successfully",
            "report_id": report_id,
            "status": status
        }), 200

    except Exception as error:

        print(
            "UPDATE STATUS ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Failed to update report status",
            "error": str(error)
        }), 500


@app.route("/api/users/<int:user_id>/reports", methods=["GET"])
def get_user_reports(user_id):

    try:

        connection = get_db_connection()

        rows = connection.execute("""
            SELECT
                id,
                user_id,
                category,
                barrier_type,
                description,
                location,
                latitude,
                longitude,
                image_path,
                severity,
                status,
                created_at
            FROM reports
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,)).fetchall()

        connection.close()

        reports = []

        for row in rows:

            reports.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "category": row["category"],
                "barrier_type": row["barrier_type"],
                "description": row["description"],
                "location": row["location"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "image": row["image_path"],
                "severity": row["severity"],
                "status": row["status"],
                "created_at": row["created_at"]
            })

        return jsonify({
            "success": True,
            "reports": reports,
            "count": len(reports)
        }), 200

    except Exception as error:

        print(
            "GET USER REPORTS ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Failed to load user reports",
            "error": str(error)
        }), 500


@app.route("/api/reports/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):

    try:

        connection = get_db_connection()

        cursor = connection.execute(
            """
            DELETE FROM reports
            WHERE id = ?
            """,
            (report_id,)
        )

        connection.commit()

        if cursor.rowcount == 0:

            connection.close()

            return jsonify({
                "success": False,
                "message": "Report not found"
            }), 404

        connection.close()

        return jsonify({
            "success": True,
            "message": "Report deleted successfully",
            "report_id": report_id
        }), 200

    except Exception as error:

        print(
            "DELETE REPORT ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "message": "Failed to delete report",
            "error": str(error)
        }), 500


# ============================================================
# GET SINGLE REPORT
# ============================================================

@app.route("/api/reports/<int:report_id>", methods=["GET"])
def get_single_report(report_id):

    try:

        connection = get_db_connection()

        row = connection.execute("""
            SELECT
                id,
                name,
                category,
                barrier_type,
                severity,
                description,
                location,
                latitude,
                longitude,
                image,
                status,
                created_at
            FROM reports
            WHERE id = ?
        """, (report_id,)).fetchone()

        connection.close()

        if row is None:

            return jsonify({
                "message": "Report not found"
            }), 404

        return jsonify({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "barrier_type": row["barrier_type"],
            "severity": row["severity"],
            "description": row["description"],
            "location": row["location"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "image": row["image"],
            "status": row["status"],
            "created_at": row["created_at"]
        }), 200

    except Exception as error:

        print("SINGLE REPORT ERROR:", error)

        return jsonify({
            "message": "Failed to load report",
            "error": str(error)
        }), 500


@app.route("/api/ai/analyze", methods=["POST"])
def ai_analyze():

    try:

        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "status": "error",
                "message": "No data received"
            }), 400

        description = str(
            data.get("description", "")
        ).strip()

        if not description:
            return jsonify({
                "status": "error",
                "message": "Description is required"
            }), 400

        result = analyze_report(
            description
        )

        return jsonify({
            "status": "success",
            "analysis": result
        }), 200

    except Exception as error:

        print(
            "AI ANALYZE ERROR:",
            error
        )

        return jsonify({
            "status": "error",
            "message": "AI analysis failed",
            "details": str(error)
        }), 500

  # ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    initialize_database()

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True
    )