import datetime
import json
import os
import tempfile
import threading
import traceback
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

app = Flask(__name__)
app.secret_key = "YOURGOAL_SECRET_KEY_CHANGE_ME"
app.config["SESSION_TYPE"] = "filesystem"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

DATA_FILE = "server_data.json"
ADMIN_FILE = "Admin.txt"
HISTORY_FILE = "history.txt"
HISTORY_FILE_LOCK = threading.Lock()

state = {"users": {}, "value_table": []}
state_lock = threading.RLock()


def append_history(actor, target, delta):
    try:
        with HISTORY_FILE_LOCK:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()}|{actor}|{target}|{delta}\n")
    except Exception as e:
        print(f"Error writing history: {e}")


def get_history(limit=50):
    try:
        with HISTORY_FILE_LOCK:
            if not os.path.exists(HISTORY_FILE):
                return []
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        entries = []
        for line in lines[-limit:]:
            parts = line.strip().split("|")
            if len(parts) == 4:
                entries.append({
                    "timestamp": parts[0],
                    "actor": parts[1],
                    "target": parts[2],
                    "delta": int(parts[3]),
                })
        return entries
    except Exception as e:
        print(f"Error reading history: {e}")
        return []


def get_admin_username():
    if not os.path.exists(ADMIN_FILE):
        return None
    try:
        with open(ADMIN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip().lower()
    except Exception:
        return None


def save_data():
    temp_name = None
    try:
        data_path = os.path.abspath(DATA_FILE)
        data_dir = os.path.dirname(data_path) or "."
        with state_lock:
            serialized = json.dumps(state, ensure_ascii=False, indent=4)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=data_dir, delete=False) as f:
            f.write(serialized)
            temp_name = f.name
        os.replace(temp_name, data_path)
    except Exception as e:
        print(f"Error saving data: {e}")
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass


def load_data():
    global state
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception as e:
            print(f"Error loading data file: {e}")
            backup_name = f"{DATA_FILE}.corrupt.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                os.rename(DATA_FILE, backup_name)
                print(f"Corrupted data backed up to {backup_name}")
            except Exception as backup_err:
                print(f"Could not back up corrupted file: {backup_err}")
            loaded = {}

        try:
            if "users" in loaded:
                state["users"] = loaded["users"]
                for u in state["users"].values():
                    if "points" not in u:
                        u["points"] = 0
            if "value_table" in loaded:
                state["value_table"] = loaded["value_table"]
            save_data()
        except Exception as e:
            print(f"Error processing data: {e}")

    if not state["users"]:
        state["users"] = {}
    if not state["value_table"]:
        state["value_table"] = []


load_data()


@app.after_request
def add_no_cache_headers(response):
    if request.path in ["/", "/login"] or request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.errorhandler(404)
def handle_404(exc):
    if request.path.startswith("/api/"):
        return jsonify({"status": "error", "message": "Not found"}), 404
    return "", 404


@app.errorhandler(405)
def handle_405(exc):
    if request.path.startswith("/api/"):
        return jsonify({"status": "error", "message": "Method not allowed"}), 405
    return "", 405


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if hasattr(exc, "code") and exc.code in (404, 405):
        return handle_404(exc) if exc.code == 404 else handle_405(exc)
    print("Unhandled server error:")
    print(traceback.format_exc())
    if request.path.startswith("/api/"):
        return jsonify({"status": "error", "message": "Erreur interne YourGoal"}), 500
    return "", 500


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        user = state["users"].get(session["username"])
        if not user or not user.get("is_active"):
            session.pop("username", None)
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def parent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        user = state["users"].get(session["username"])
        if not user or not user.get("is_active") or user.get("role") not in ("parent", "admin"):
            return jsonify({"status": "error", "message": "Parents only"}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_json_body():
    return request.get_json(silent=True) or {}


def is_parent(username):
    user = state["users"].get(username)
    return user and user.get("role") in ("parent", "admin")


def is_admin(username):
    user = state["users"].get(username)
    return user and user.get("is_admin", False)


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").lower().strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "child").lower().strip()
        action = request.form.get("action")

        if action == "register":
            if username in state["users"]:
                return render_template("login.html", error="Ce nom existe deja.")

            root_admin = get_admin_username()
            is_admin_user = False
            is_active = False

            if role == "parent":
                if root_admin is None and len(state["users"]) == 0:
                    is_admin_user = True
                    is_active = True
                    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
                        f.write(username)
                elif root_admin and username == root_admin:
                    is_admin_user = True
                    is_active = True
                else:
                    return render_template("login.html", error="Seul l'admin peut creer des parents.")
            else:
                is_active = True

            state["users"][username] = {
                "password": password,
                "role": role,
                "display_name": (request.form.get("display_name") or username).strip(),
                "is_active": is_active,
                "is_admin": is_admin_user,
                "points": 0,
                "avatar": "",
            }
            save_data()

            if is_active:
                session["username"] = username
                session.permanent = True
                return redirect(url_for("index"))
            return render_template("login.html", message="Compte cree. Attente validation.")

        if action == "login":
            user = state["users"].get(username)
            if user and user["password"] == password:
                if not user.get("is_active"):
                    return render_template("login.html", error="Compte en attente.")
                session["username"] = username
                session.permanent = True
                return redirect(url_for("index"))
            return render_template("login.html", error="Erreur identifiants.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


@app.route("/api/whoami")
@login_required
def whoami():
    user = state["users"][session["username"]]
    children = []
    if is_parent(session["username"]):
        children = [
            {"username": u, "display_name": d["display_name"], "points": d.get("points", 0), "avatar": d.get("avatar", "")}
            for u, d in state["users"].items() if d.get("role") == "child"
        ]
    return jsonify({
        "username": session["username"],
        "display_name": user.get("display_name", session["username"]),
        "role": user.get("role"),
        "is_admin": user.get("is_admin", False),
        "points": user.get("points", 0),
        "avatar": user.get("avatar", ""),
        "children": children,
        "value_table": state.get("value_table", []),
        "all_users": [
            {"username": u, "display_name": d["display_name"], "role": d.get("role"), "points": d.get("points", 0), "avatar": d.get("avatar", "")}
            for u, d in state["users"].items()
        ] if is_parent(session["username"]) else [],
    })


# ─── VALUE TABLE ──────────────────────────────────────────────────────────────

@app.route("/api/values/save", methods=["POST"])
@login_required
@parent_required
def save_values():
    data = get_json_body()
    state["value_table"] = data.get("value_table", [])
    save_data()
    return jsonify({"status": "ok", "value_table": state["value_table"]})


# ─── POINTS ADJUSTMENT ────────────────────────────────────────────────────────

@app.route("/api/users/adjust_points", methods=["POST"])
@login_required
@parent_required
def adjust_points():
    data = get_json_body()
    username = (data.get("username") or "").lower().strip()
    try:
        delta = int(data.get("delta", 1))
    except (TypeError, ValueError):
        delta = 1
    if username in state["users"]:
        state["users"][username]["points"] = state["users"][username].get("points", 0) + delta
        append_history(session["username"], username, delta)
        save_data()
        points = state["users"][username]["points"]
        return jsonify({"status": "ok", "points": points})
    return jsonify({"status": "error"}), 404


@app.route("/api/history")
@login_required
@parent_required
def history():
    return jsonify({"history": get_history()})


# ─── USERS MANAGEMENT ─────────────────────────────────────────────────────────

@app.route("/api/users/add", methods=["POST"])
@login_required
@parent_required
def add_user():
    data = get_json_body()
    username = (data.get("username") or "").lower().strip()
    password = data.get("password") or ""
    role = (data.get("role") or "child").strip().lower()
    display_name = (data.get("display_name") or username).strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "Login et mot de passe requis"}), 400
    if username in state["users"]:
        return jsonify({"status": "error", "message": "Ce nom existe deja"}), 400
    if role not in ("parent", "child"):
        role = "child"

    is_admin_user = False
    if role == "parent":
        root_admin = get_admin_username()
        if root_admin and session["username"] == root_admin:
            is_admin_user = True

    state["users"][username] = {
        "password": password,
        "role": role,
        "display_name": display_name,
        "is_active": True,
        "is_admin": is_admin_user,
        "points": 0,
        "avatar": "",
    }
    save_data()
    return jsonify({"status": "ok"})


@app.route("/api/settings", methods=["POST"])
@login_required
def update_settings():
    data = get_json_body()
    target = data.get("target_username", "").lower().strip()
    if target and target != session["username"]:
        if not is_parent(session["username"]):
            return jsonify({"status": "error", "message": "Parents seulement"}), 403
        user = state["users"].get(target)
        if not user:
            return jsonify({"status": "error", "message": "Utilisateur inconnu"}), 404
    else:
        user = state["users"][session["username"]]
    if "avatar" in data:
        user["avatar"] = data["avatar"]
    if "display_name" in data:
        user["display_name"] = data["display_name"]
    save_data()
    return jsonify({"status": "ok"})


@app.route("/api/users/delete", methods=["POST"])
@login_required
@parent_required
def delete_user():
    data = get_json_body()
    username = (data.get("username") or "").lower().strip()
    if username not in state["users"]:
        return jsonify({"status": "error"}), 404
    if state["users"][username].get("is_admin"):
        return jsonify({"status": "error", "message": "Impossible de supprimer l'admin"}), 400
    del state["users"][username]
    save_data()
    return jsonify({"status": "ok"})


# ─── STATIC FILES ────────────────────────────────────────────────────────────

@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory("static", "manifest.json", mimetype="application/json")


@app.route("/sw.js")
def serve_sw():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


@app.route("/favicon.ico")
def serve_favicon():
    return send_from_directory("static", "favicon.ico")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    try:
        from waitress import serve as waitress_serve
        print(f"YourGoal Web App running on port {port} (Waitress)")
        waitress_serve(app, host="0.0.0.0", port=port, threads=8)
    except ImportError:
        try:
            import subprocess, sys
            subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress", "--quiet"])
            from waitress import serve as waitress_serve
            print(f"YourGoal Web App running on port {port} (Waitress)")
            waitress_serve(app, host="0.0.0.0", port=port, threads=8)
        except Exception as e:
            print(f"YourGoal Web App running on port {port} (Flask dev server)")
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
