import datetime
import json
import os
import tempfile
import threading
import traceback
import uuid
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

app = Flask(__name__)
app.secret_key = "YOURGOAL_SECRET_KEY_CHANGE_ME"
app.config["SESSION_TYPE"] = "filesystem"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

DATA_FILE = "server_data.json"
ADMIN_FILE = "Admin.txt"

state = {"users": {}, "tasks": [], "rewards": [], "counters": []}
state_lock = threading.RLock()


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
                    if "counters" not in u:
                        u["counters"] = {}
                    if "points" not in u:
                        u["points"] = 0
            if "tasks" in loaded:
                state["tasks"] = loaded["tasks"]
            if "rewards" in loaded:
                state["rewards"] = loaded["rewards"]
            if "counters" in loaded:
                state["counters"] = loaded["counters"]
            save_data()
        except Exception as e:
            print(f"Error processing data: {e}")

    if not state["users"]:
        state["users"] = {}
    if not state["tasks"]:
        state["tasks"] = []
    if not state["rewards"]:
        state["rewards"] = []
    if not state["counters"]:
        state["counters"] = []


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
                "counters": {},
                "avatar": "",
                "history": [],
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
            {"username": u, "display_name": d["display_name"], "points": d.get("points", 0), "counters": d.get("counters", {}), "avatar": d.get("avatar", ""), "history": d.get("history", []), "alerts": d.get("alerts", {})}
            for u, d in state["users"].items() if d.get("role") == "child"
        ]
    return jsonify({
        "username": session["username"],
        "display_name": user.get("display_name", session["username"]),
        "role": user.get("role"),
        "is_admin": user.get("is_admin", False),
        "points": user.get("points", 0),
        "counters": user.get("counters", {}),
        "avatar": user.get("avatar", ""),
        "history": user.get("history", []),
        "alerts": user.get("alerts", {}),
        "children": children,
        "all_users": [
            {"username": u, "display_name": d["display_name"], "role": d.get("role"), "points": d.get("points", 0), "counters": d.get("counters", {}), "avatar": d.get("avatar", ""), "history": d.get("history", []), "alerts": d.get("alerts", {})}
            for u, d in state["users"].items()
        ] if is_parent(session["username"]) else [],
    })


# ─── TASKS ───────────────────────────────────────────────────────────────────

def task_status_color(status):
    return {
        "proposed": "#888888",
        "in_progress": "#e67e22",
        "completed": "#f1c40f",
        "validated": "#2ecc71",
        "rejected": "#e74c3c",
    }.get(status, "#888888")


@app.route("/api/tasks")
@login_required
def list_tasks():
    user = state["users"][session["username"]]
    is_par = is_parent(session["username"])
    tasks = []
    for t in state["tasks"]:
        t_out = dict(t)
        if not is_par:
            if t.get("assigned_to") and t["assigned_to"] != session["username"]:
                if t["status"] in ("in_progress", "completed", "validated"):
                    continue
            if t["status"] == "rejected":
                continue
        t_out["color"] = task_status_color(t["status"])
        tasks.append(t_out)
    return jsonify({"tasks": tasks})


@app.route("/api/tasks/add", methods=["POST"])
@login_required
@parent_required
def add_task():
    data = get_json_body()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"status": "error", "message": "Titre requis"}), 400
    try:
        points = int(data.get("points", 1))
    except (TypeError, ValueError):
        points = 1
    assigned_to = data.get("assigned_to", "").strip().lower()

    recurring = data.get("recurring", False)
    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "points": max(1, points),
        "status": "proposed",
        "recurring": recurring,
        "assigned_to": assigned_to if assigned_to and assigned_to in state["users"] else None,
        "created_by": session["username"],
        "claimed_by": None,
        "created_at": datetime.datetime.now().isoformat(),
    }
    state["tasks"].append(task)
    save_data()
    return jsonify({"status": "ok", "task": task})


@app.route("/api/tasks/claim", methods=["POST"])
@login_required
def claim_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            if t["status"] != "proposed":
                return jsonify({"status": "error", "message": "Tache deja prise"}), 400
            if t.get("assigned_to") and t["assigned_to"] != session["username"]:
                return jsonify({"status": "error", "message": "Tache pas pour toi"}), 400
            t["status"] = "in_progress"
            t["claimed_by"] = session["username"]
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/complete", methods=["POST"])
@login_required
def complete_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            if t.get("claimed_by") != session["username"]:
                return jsonify({"status": "error", "message": "Pas ta tache"}), 400
            if t["status"] != "in_progress":
                return jsonify({"status": "error", "message": "Mauvais statut"}), 400
            t["status"] = "completed"
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/validate", methods=["POST"])
@login_required
@parent_required
def validate_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            if t["status"] != "completed":
                return jsonify({"status": "error", "message": "Mauvais statut"}), 400
            t["status"] = "validated"
            t["validated_by"] = session["username"]
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/reject", methods=["POST"])
@login_required
@parent_required
def reject_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            if t["status"] != "completed":
                return jsonify({"status": "error", "message": "Mauvais statut"}), 400
            t["status"] = "rejected"
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/improve", methods=["POST"])
@login_required
@parent_required
def improve_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            if t["status"] != "completed":
                return jsonify({"status": "error", "message": "Mauvais statut"}), 400
            t["status"] = "in_progress"
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/claim_points", methods=["POST"])
@login_required
def claim_points():
    data = get_json_body()
    task_id = data.get("id")
    for idx, t in enumerate(state["tasks"]):
        if t["id"] == task_id:
            if t["status"] != "validated":
                return jsonify({"status": "error", "message": "Pas encore valide"}), 400
            child = t.get("claimed_by")
            if child != session["username"]:
                return jsonify({"status": "error", "message": "Pas ta tache"}), 400
            if child in state["users"]:
                state["users"][child]["points"] = state["users"][child].get("points", 0) + t["points"]
                if "history" not in state["users"][child]:
                    state["users"][child]["history"] = []
                state["users"][child]["history"].append({
                    "title": t["title"],
                    "points": t["points"],
                    "timestamp": datetime.datetime.now().isoformat(),
                })
            if t.get("recurring"):
                t["status"] = "proposed"
                t["claimed_by"] = None
            else:
                state["tasks"].pop(idx)
            save_data()
            return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/reset", methods=["POST"])
@login_required
@parent_required
def reset_task():
    data = get_json_body()
    task_id = data.get("id")
    for t in state["tasks"]:
        if t["id"] == task_id:
            t["status"] = "proposed"
            t["claimed_by"] = None
            save_data()
            return jsonify({"status": "ok", "task": t})
    return jsonify({"status": "error"}), 404


@app.route("/api/tasks/delete", methods=["POST"])
@login_required
@parent_required
def delete_task():
    data = get_json_body()
    task_id = data.get("id")
    for idx, t in enumerate(state["tasks"]):
        if t["id"] == task_id:
            state["tasks"].pop(idx)
            save_data()
            return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404


# ─── COUNTERS ────────────────────────────────────────────────────────────────

@app.route("/api/counters")
@login_required
def list_counters():
    return jsonify({"counters": state["counters"]})


@app.route("/api/counters/add", methods=["POST"])
@login_required
@parent_required
def add_counter():
    data = get_json_body()
    name = data.get("name", "").strip()
    unit = data.get("unit", "").strip()
    if not name:
        return jsonify({"status": "error", "message": "Nom requis"}), 400
    try:
        division = int(data.get("division", 1))
    except (TypeError, ValueError):
        division = 1
    try:
        price = int(data.get("price", 10))
    except (TypeError, ValueError):
        price = 10
    counter = {
        "id": str(uuid.uuid4()),
        "name": name,
        "unit": unit or name,
        "division": max(1, division),
        "price": max(1, price),
        "created_by": session["username"],
    }
    state["counters"].append(counter)
    save_data()
    return jsonify({"status": "ok", "counter": counter})


@app.route("/api/counters/edit", methods=["POST"])
@login_required
@parent_required
def edit_counter():
    data = get_json_body()
    counter_id = data.get("id")
    for c in state["counters"]:
        if c["id"] == counter_id:
            if "name" in data and data["name"].strip():
                c["name"] = data["name"].strip()
            if "unit" in data and data["unit"].strip():
                c["unit"] = data["unit"].strip()
            try:
                if "division" in data:
                    c["division"] = max(1, int(data["division"]))
                if "price" in data:
                    c["price"] = max(1, int(data["price"]))
            except (TypeError, ValueError):
                pass
            save_data()
            return jsonify({"status": "ok", "counter": c})
    return jsonify({"status": "error"}), 404


@app.route("/api/counters/delete", methods=["POST"])
@login_required
@parent_required
def delete_counter():
    data = get_json_body()
    counter_id = data.get("id")
    for idx, c in enumerate(state["counters"]):
        if c["id"] == counter_id:
            state["counters"].pop(idx)
            save_data()
            return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404


# ─── CHILD COUNTERS ──────────────────────────────────────────────────────────

@app.route("/api/child_counters", methods=["POST"])
@login_required
@parent_required
def child_counters():
    data = get_json_body()
    child_username = data.get("child", "").lower().strip()
    child = state["users"].get(child_username)
    if not child or child.get("role") != "child":
        return jsonify({"status": "error"}), 404
    return jsonify({"status": "ok", "counters": child.get("counters", {})})


@app.route("/api/child_counters/use", methods=["POST"])
@login_required
@parent_required
def use_counter():
    data = get_json_body()
    child_username = data.get("child", "").lower().strip()
    counter_id = data.get("counter_id")
    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0

    child = state["users"].get(child_username)
    if not child or child.get("role") != "child":
        return jsonify({"status": "error"}), 404

    if "counters" not in child:
        child["counters"] = {}
    if counter_id not in child["counters"]:
        child["counters"][counter_id] = 0
    child["counters"][counter_id] += amount
    save_data()
    return jsonify({"status": "ok", "counters": child["counters"]})


@app.route("/api/child_counters/reset", methods=["POST"])
@login_required
@parent_required
def reset_counter():
    data = get_json_body()
    child_username = data.get("child", "").lower().strip()
    counter_id = data.get("counter_id")
    child = state["users"].get(child_username)
    if not child or child.get("role") != "child":
        return jsonify({"status": "error"}), 404
    if "counters" in child and counter_id in child["counters"]:
        child["counters"][counter_id] = 0
        save_data()
    return jsonify({"status": "ok", "counters": child.get("counters", {})})


# ─── ALERTS (parent → child messages) ───────────────────────────────────────

@app.route("/api/child_alert/set", methods=["POST"])
@login_required
@parent_required
def set_alert():
    data = get_json_body()
    child_username = data.get("child", "").lower().strip()
    message = data.get("message", "").strip()
    counter_id = data.get("counter_id", "")
    child = state["users"].get(child_username)
    if not child or child.get("role") != "child":
        return jsonify({"status": "error"}), 404
    if not message:
        return jsonify({"status": "error", "message": "Message vide"}), 400
    if "alerts" not in child:
        child["alerts"] = {}
    child["alerts"][counter_id] = {
        "message": message,
        "timestamp": datetime.datetime.now().isoformat(),
        "created_by": session["username"],
    }
    save_data()
    return jsonify({"status": "ok"})


@app.route("/api/child_alert/clear", methods=["POST"])
@login_required
@parent_required
def clear_alert():
    data = get_json_body()
    child_username = data.get("child", "").lower().strip()
    counter_id = data.get("counter_id", "")
    child = state["users"].get(child_username)
    if not child:
        return jsonify({"status": "error"}), 404
    if "alerts" in child and counter_id in child["alerts"]:
        del child["alerts"][counter_id]
        save_data()
    return jsonify({"status": "ok"})


@app.route("/api/child_alert/ack", methods=["POST"])
@login_required
def ack_alert():
    data = get_json_body()
    counter_id = data.get("counter_id", "")
    child = state["users"].get(session["username"])
    if not child or child.get("role") != "child":
        return jsonify({"status": "error"}), 400
    if "alerts" in child and counter_id in child["alerts"]:
        del child["alerts"][counter_id]
        save_data()
    return jsonify({"status": "ok"})


# ─── REDEEM (child spends points) ───────────────────────────────────────────

@app.route("/api/redeem", methods=["POST"])
@login_required
def redeem():
    data = get_json_body()
    counter_id = data.get("counter_id")
    counter_obj = None
    for c in state["counters"]:
        if c["id"] == counter_id:
            counter_obj = c
            break
    if not counter_obj:
        return jsonify({"status": "error", "message": "Compteur inconnu"}), 404

    child = state["users"][session["username"]]
    if child.get("role") != "child":
        return jsonify({"status": "error", "message": "Enfants seulement"}), 400

    price = counter_obj["price"]
    if child.get("points", 0) < price:
        return jsonify({"status": "error", "message": "Pas assez de points"}), 400

    child["points"] -= price
    if "counters" not in child:
        child["counters"] = {}
    if counter_id not in child["counters"]:
        child["counters"][counter_id] = 0
    child["counters"][counter_id] += counter_obj["division"]

    save_data()
    return jsonify({"status": "ok", "points": child["points"], "counters": child.get("counters", {})})


# ─── USERS MANAGEMENT ────────────────────────────────────────────────────────

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
        "counters": {},
        "avatar": "",
        "history": [],
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


@app.route("/api/users/update_points", methods=["POST"])
@login_required
@parent_required
def update_points():
    data = get_json_body()
    username = (data.get("username") or "").lower().strip()
    try:
        points = int(data.get("points", 0))
    except (TypeError, ValueError):
        points = 0
    if username in state["users"]:
        state["users"][username]["points"] = points
        save_data()
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404


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
