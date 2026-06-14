# ========== app.py (পুরো ফাইল ঠিক করা) ==========

import os
import json
import signal
import subprocess
import shutil
import zipfile
import hashlib
import psutil
import threading
import time
import urllib.request
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort
import io

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
SERVERS_DIR = BASE_DIR / "servers"
SERVERS_DIR.mkdir(exist_ok=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "JIHADX24")
NORMAL_PASSWORD = os.environ.get("NORMAL_PASSWORD", "00")

RUNNING_PROCESSES = {}
RESET_TIMERS = {}

THEME_PRESETS = {
    "purple": "#a855f7",
    "green": "#00ff41",
    "blue": "#38bdf8",
    "red": "#ef4444",
    "amber": "#fbbf24",
    "cyan": "#06b6d4",
    "pink": "#ec4899",
    "lime": "#84cc16",
    "neon": "#ff00ff",
    "orange": "#ff6b00",
    "violet": "#8b00ff",
    "gold": "#ffd700",
}

ALL_PACKAGES = {
    "python": [
        "flask", "fastapi", "django", "requests", "aiohttp", "discord.py",
        "python-telegram-bot", "tweepy", "pandas", "numpy", "matplotlib",
        "scikit-learn", "sqlalchemy", "psycopg2", "pymongo", "redis",
        "celery", "pydantic", "httpx", "openai", "anthropic", "langchain",
        "beautifulsoup4", "selenium", "scrapy", "pillow", "opencv-python",
        "tensorflow", "torch", "transformers", "gradio", "streamlit",
        "plotly", "seaborn", "jupyter", "ipython", "flask-socketio",
        "websockets", "asyncio", "uvicorn", "gunicorn", "werkzeug",
        "jinja2", "click", "colorama", "tqdm", "schedule", "apscheduler"
    ],
    "node": [
        "express", "discord.js", "axios", "dotenv", "nodemon", "mongoose",
        "socket.io", "jsonwebtoken", "bcryptjs", "cors", "helmet", "morgan",
        "body-parser", "ejs", "pug", "handlebars", "react", "vue", "angular",
        "next", "nuxt", "pm2", "forever", "webpack", "vite", "typescript",
        "ts-node", "nodemailer", "passport", "multer", "sharp", "puppeteer"
    ],
    "static": [
        "live-server", "http-server", "serve", "browser-sync"
    ]
}

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except Exception:
            pass
    return {
        "servers": {},
        "users": {},
        "settings": {
            "maintenance": False,
            "maintenance_msg": "System under maintenance.",
            "theme_color": "#a855f7",
            "admin_password": ADMIN_PASSWORD,
            "normal_password": NORMAL_PASSWORD,
            "site_name": "—͞JIHꫝDX"
        }
     𝐂𝚘𝙳𝚎𝚡"
        }
    }

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str))

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def get_theme_color():
    data = load_data()
    return data.get("settings", {}).get("theme_color", "#a855f7")

@app.context_processor
def inject_theme():
    return {"theme_color": get_theme_color()}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        data = load_data()
        settings = data.get("settings", {})
        if settings.get("maintenance") and session.get("username") != "__admin__":
            return render_template("maintenance.html", message=settings.get("maintenance_msg", "Under maintenance"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def is_process_alive(pid):
    try:
        if not pid:
            return False
        p = psutil.Process(pid)
        return p.is_running() and p.status() not in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def kill_process(pid):
    try:
        p = psutil.Process(pid)
        children = p.children(recursive=True)
        p.terminate()
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
        try:
            p.wait(timeout=5)
        except psutil.TimeoutExpired:
            p.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

def get_run_command(runtime, main_file):
    ext = Path(main_file).suffix.lower()
    if runtime == "node" or ext in (".js", ".ts", ".mjs"):
        return ["node", main_file]
    elif runtime == "static":
        return ["python", "-m", "http.server", "8080"]
    else:
        return ["python", "-u", main_file]

def _sync_process_status():
    data = load_data()
    changed = False
    for name, cfg in data["servers"].items():
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
            changed = True
    if changed:
        save_data(data)

_sync_process_status()

def _auto_reset_seconds(cfg):
    ar = cfg.get("auto_reset", {})
    y = ar.get("years", 0) or 0
    d = ar.get("days", 0) or 0
    h = ar.get("hours", 0) or 0
    m = ar.get("minutes", 0) or 0
    s = ar.get("seconds", 0) or 0
    return int(y * 365 * 24 * 3600 + d * 24 * 3600 + h * 3600 + m * 60 + s)

def _do_auto_reset(name):
    try:
        data = load_data()
        cfg = data["servers"].get(name)
        if not cfg:
            return
        
        # Stop current process
        pid = cfg.get("pid")
        if name in RUNNING_PROCESSES:
            entry = RUNNING_PROCESSES[name]
            proc = entry["proc"]
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                entry["log_file"].close()
            except Exception:
                pass
            del RUNNING_PROCESSES[name]
        elif pid:
            kill_process(pid)

        log_path = SERVERS_DIR / name / "logs.txt"
        try:
            with open(log_path, "a") as lf:
                lf.write(f"\n{'='*50}\n[{datetime.now().isoformat()}] AUTO RESET triggered\n{'='*50}\n")
        except Exception:
            pass

        # Start again
        main_file = cfg.get("main_file") or "main.py"
        main_cmd = cfg.get("main_command") or ""
        extract_dir = SERVERS_DIR / name / "extracted"
        main_path = extract_dir / main_file
        if main_path.exists():
            if main_cmd:
                cmd = main_cmd.split()
            else:
                cmd = get_run_command(cfg.get("runtime", "python"), main_file)
            env = os.environ.copy()
            env["PORT"] = str(cfg.get("port", 8080))
            log_file = open(log_path, "a")
            proc = subprocess.Popen(cmd, cwd=str(extract_dir), stdout=log_file, stderr=log_file, env=env, preexec_fn=os.setsid)
            RUNNING_PROCESSES[name] = {"proc": proc, "log_file": log_file}
            cfg["status"] = "running"
            cfg["pid"] = proc.pid
        else:
            cfg["status"] = "stopped"
            cfg["pid"] = None

        data["servers"][name] = cfg
        save_data(data)

        total = _auto_reset_seconds(cfg)
        if cfg.get("auto_reset", {}).get("enabled") and total > 0:
            _schedule_reset(name, total)
    except Exception:
        pass

def _schedule_reset(name, total_seconds):
    if name in RESET_TIMERS:
        try:
            RESET_TIMERS[name]["timer"].cancel()
        except Exception:
            pass
    t = threading.Timer(total_seconds, _do_auto_reset, args=[name])
    t.daemon = True
    t.start()
    RESET_TIMERS[name] = {
        "timer": t,
        "started_at": datetime.now().isoformat(),
        "total_seconds": total_seconds
    }

def _init_reset_timers():
    data = load_data()
    for name, cfg in data["servers"].items():
        ar = cfg.get("auto_reset", {})
        if ar.get("enabled"):
            total = _auto_reset_seconds(cfg)
            if total > 0:
                _schedule_reset(name, total)

_init_reset_timers()

@app.route("/api/ping")
def ping():
    return "pong", 200

def keep_alive():
    while True:
        time.sleep(240)
        try:
            url = os.environ.get("RENDER_EXTERNAL_URL")
            if url:
                ping_url = f"{url}/api/ping"
            else:
                port = os.environ.get("PORT", 5000)
                ping_url = f"http://127.0.0.1:{port}/api/ping"
            req = urllib.request.Request(ping_url, headers={'User-Agent': 'KeepAlive-Bot/1.0'})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

threading.Thread(target=keep_alive, daemon=True).start()

@app.route("/")
def index():
    if session.get("username"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not username:
            return render_template("login.html", error="Enter a username")
        
        data = load_data()
        settings = data.get("settings", {})
        normal_pass = settings.get("normal_password", NORMAL_PASSWORD)
        
        # Password must match exactly - no automatic login without correct password
        if password != normal_pass:
            return render_template("login.html", error="Wrong password")
        
        # Password is correct, now handle user
        user = data["users"].get(username)
        if not user:
            # Create new user with hashed password
            data["users"][username] = {
                "joined": datetime.now().isoformat(),
                "password_hash": hash_password(password)
            }
            save_data(data)
        else:
            # Update password hash if needed (for existing users)
            if user.get("password_hash") != hash_password(password):
                data["users"][username]["password_hash"] = hash_password(password)
                save_data(data)
        
        session["username"] = username
        return redirect(url_for("dashboard"))
    
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    username = session["username"]
    data = load_data()
    settings = data.get("settings", {})
    site_name = settings.get("site_name", "—͞SᎻꫝᎮᎮƝ᥆ꤪꤨ 𝐂𝚘𝙳𝚎𝚡")
    user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
    changed = False
    for name, cfg in user_servers.items():
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
            data["servers"][name] = cfg
            changed = True
    if changed:
        save_data(data)
    running = sum(1 for v in user_servers.values() if v.get("status") == "running")
    return render_template("dashboard.html", servers=user_servers, running=running, total=len(user_servers), username=username, site_name=site_name)

@app.route("/api/stats")
@login_required
def system_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    return jsonify({"cpu": cpu, "ram": ram, "disk": disk})

@app.route("/server/create", methods=["POST"])
@login_required
def create_server():
    name = request.form.get("name", "").strip().replace(" ", "-")
    runtime = request.form.get("runtime", "python")
    if not name:
        return redirect(url_for("dashboard"))
    data = load_data()
    if name in data["servers"]:
        return redirect(url_for("dashboard"))
    cfg = {
        "name": name,
        "owner": session["username"],
        "runtime": runtime,
        "status": "stopped",
        "main_file": "",
        "main_command": "",
        "port": 8080,
        "packages": [],
        "pid": None,
        "created": datetime.now().isoformat(),
        "auto_reset": {"enabled": False, "years": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    }
    data["servers"][name] = cfg
    save_data(data)
    (SERVERS_DIR / name / "extracted").mkdir(parents=True, exist_ok=True)
    return redirect(url_for("server_detail", name=name))

@app.route("/server/delete/<name>", methods=["POST"])
@login_required
def delete_server(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if cfg and (cfg.get("owner") == session["username"] or session.get("admin")):
        pid = cfg.get("pid")
        if pid:
            kill_process(pid)
        if name in RUNNING_PROCESSES:
            try:
                RUNNING_PROCESSES[name]["proc"].terminate()
                RUNNING_PROCESSES[name]["log_file"].close()
            except Exception:
                pass
            del RUNNING_PROCESSES[name]
        if name in RESET_TIMERS:
            try:
                RESET_TIMERS[name]["timer"].cancel()
            except Exception:
                pass
            del RESET_TIMERS[name]
        del data["servers"][name]
        save_data(data)
        shutil.rmtree(SERVERS_DIR / name, ignore_errors=True)
    return redirect(url_for("dashboard"))

@app.route("/server/<name>")
@login_required
def server_detail(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return "Server not found", 404
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return "Access denied", 403
    pid = cfg.get("pid")
    if pid and not is_process_alive(pid):
        cfg["status"] = "stopped"
        cfg["pid"] = None
        data["servers"][name] = cfg
        save_data(data)
    if "auto_reset" not in cfg:
        cfg["auto_reset"] = {"enabled": False, "years": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    if "main_command" not in cfg:
        cfg["main_command"] = ""
    extract_dir = SERVERS_DIR / name / "extracted"
    files = list_files(extract_dir)
    return render_template("server.html", server_name=name, config=cfg, files=files)

def list_files(directory, base=""):
    result = []
    if not directory.exists():
        return result
    try:
        for entry in sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name)):
            rel = f"{base}/{entry.name}" if base else entry.name
            if entry.is_dir():
                result.append({"name": entry.name, "path": rel, "type": "dir", "size": 0})
                result.extend(list_files(entry, rel))
            else:
                result.append({"name": entry.name, "path": rel, "type": "file", "size": entry.stat().st_size})
    except Exception:
        pass
    return result

@app.route("/server/<name>/upload", methods=["POST"])
@login_required
def upload_file(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"success": False, "error": "Empty filename"}), 400
    
    extract_dir = SERVERS_DIR / name / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    upload_path = SERVERS_DIR / name / f"upload_{f.filename}"
    f.save(upload_path)
    
    extracted_files = []
    
    if f.filename.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(upload_path, "r") as z:
                # Security check - prevent path traversal
                for member in z.infolist():
                    if member.filename.startswith(("/", "\\", "..", "../")):
                        upload_path.unlink(missing_ok=True)
                        return jsonify({"success": False, "error": "Invalid zip path"})
                
                z.extractall(extract_dir)
                for member in z.infolist():
                    if not member.is_dir():
                        extracted_files.append(member.filename)
            upload_path.unlink(missing_ok=True)
        except Exception as e:
            upload_path.unlink(missing_ok=True)
            return jsonify({"success": False, "error": f"Zip extraction failed: {str(e)}"}), 500
    else:
        dest = extract_dir / f.filename
        shutil.move(str(upload_path), str(dest))
        extracted_files = [f.filename]
        # Auto-set main file if not set and file is executable
        if not cfg.get("main_file") and f.filename.endswith((".py", ".js", ".ts")):
            cfg["main_file"] = f.filename
            data["servers"][name] = cfg
            save_data(data)
    
    return jsonify({"success": True, "files": extracted_files, "count": len(extracted_files)})

@app.route("/server/<name>/packages/install", methods=["POST"])
@login_required
def install_package(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    payload = request.get_json()
    pkg_name = payload.get("name", "").strip()
    pkg_ver = payload.get("version", "").strip()
    runtime = cfg.get("runtime", "python")
    
    if not pkg_name:
        return jsonify({"success": False, "error": "Package name required"})
    
    install_str = f"{pkg_name}=={pkg_ver}" if pkg_ver else pkg_name
    
    try:
        if runtime == "python":
            result = subprocess.run(["pip", "install", install_str], capture_output=True, text=True, timeout=120)
        elif runtime == "node":
            result = subprocess.run(["npm", "install", pkg_name] + (["@", pkg_ver] if pkg_ver else []), capture_output=True, text=True, timeout=120, cwd=str(SERVERS_DIR / name / "extracted"))
        else:
            result = subprocess.run(["npm", "install", "-g", pkg_name] + (["@", pkg_ver] if pkg_ver else []), capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            return jsonify({"success": False, "error": result.stderr[:500] or result.stdout[:500]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
    pkgs = cfg.get("packages", [])
    pkgs = [p for p in pkgs if p["name"] != pkg_name]
    pkgs.append({"name": pkg_name, "version": pkg_ver or "", "installed_at": datetime.now().isoformat(), "runtime": runtime})
    cfg["packages"] = pkgs
    data["servers"][name] = cfg
    save_data(data)
    
    # Update requirements.txt for Python projects
    if runtime == "python":
        req_path = SERVERS_DIR / name / "extracted" / "requirements.txt"
        try:
            lines = req_path.read_text().splitlines() if req_path.exists() else []
            lines = [l for l in lines if not l.lower().startswith(pkg_name.lower())]
            lines.append(install_str)
            req_path.write_text("\n".join(lines) + "\n")
        except Exception:
            pass
    
    return jsonify({"success": True, "package": pkg_name})

@app.route("/admin/packages/install-all", methods=["POST"])
@admin_required
def install_all_packages():
    results = {"python": [], "node": [], "static": [], "failed": []}
    
    # Install Python packages
    for pkg in ALL_PACKAGES["python"]:
        try:
            result = subprocess.run(["pip", "install", pkg], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                results["python"].append(pkg)
            else:
                results["failed"].append(f"python:{pkg}")
        except Exception:
            results["failed"].append(f"python:{pkg}")
    
    # Install Node.js packages globally
    for pkg in ALL_PACKAGES["node"]:
        try:
            result = subprocess.run(["npm", "install", "-g", pkg], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                results["node"].append(pkg)
            else:
                results["failed"].append(f"node:{pkg}")
        except Exception:
            results["failed"].append(f"node:{pkg}")
    
    # Install static server packages
    for pkg in ALL_PACKAGES["static"]:
        try:
            result = subprocess.run(["npm", "install", "-g", pkg], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                results["static"].append(pkg)
            else:
                results["failed"].append(f"static:{pkg}")
        except Exception:
            results["failed"].append(f"static:{pkg}")
    
    return jsonify({
        "success": True, 
        "installed": results["python"] + results["node"] + results["static"],
        "python_count": len(results["python"]),
        "node_count": len(results["node"]),
        "static_count": len(results["static"]),
        "failed": results["failed"]
    })

@app.route("/server/<name>/packages/remove", methods=["POST"])
@login_required
def remove_package(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False}), 403
    
    payload = request.get_json()
    pkg_name = payload.get("name", "")
    cfg["packages"] = [p for p in cfg.get("packages", []) if p["name"] != pkg_name]
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})

@app.route("/server/<name>/settings", methods=["POST"])
@login_required
def save_settings(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    payload = request.get_json()
    cfg["main_file"] = payload.get("main_file", cfg.get("main_file", ""))
    cfg["main_command"] = payload.get("main_command", cfg.get("main_command", ""))
    cfg["port"] = payload.get("port", cfg.get("port", 8080))
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})

@app.route("/server/<name>/auto-reset/settings", methods=["POST"])
@login_required
def save_auto_reset_settings(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    payload = request.get_json()
    enabled = bool(payload.get("enabled", False))
    years = int(payload.get("years", 0) or 0)
    days = int(payload.get("days", 0) or 0)
    hours = int(payload.get("hours", 0) or 0)
    minutes = int(payload.get("minutes", 0) or 0)
    seconds = int(payload.get("seconds", 0) or 0)
    
    cfg["auto_reset"] = {"enabled": enabled, "years": years, "days": days, "hours": hours, "minutes": minutes, "seconds": seconds}
    data["servers"][name] = cfg
    save_data(data)
    
    if name in RESET_TIMERS:
        try:
            RESET_TIMERS[name]["timer"].cancel()
        except Exception:
            pass
        del RESET_TIMERS[name]
    
    if enabled:
        total = _auto_reset_seconds(cfg)
        if total > 0:
            _schedule_reset(name, total)
    
    return jsonify({"success": True})

@app.route("/server/<name>/auto-reset", methods=["POST"])
@login_required
def trigger_auto_reset(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    threading.Thread(target=_do_auto_reset, args=[name], daemon=True).start()
    return jsonify({"success": True})

@app.route("/server/<name>/auto-reset/status")
@login_required
def auto_reset_status(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"remaining": 0, "total": 0})
    
    if name in RESET_TIMERS:
        entry = RESET_TIMERS[name]
        started = datetime.fromisoformat(entry["started_at"])
        elapsed = (datetime.now() - started).total_seconds()
        remaining = max(0, entry["total_seconds"] - int(elapsed))
        return jsonify({"remaining": remaining, "total": entry["total_seconds"]})
    
    total = _auto_reset_seconds(cfg)
    return jsonify({"remaining": total, "total": total})

@app.route("/server/<name>/start", methods=["POST"])
@login_required
def start_server(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    
    pid = cfg.get("pid")
    if pid and is_process_alive(pid):
        return jsonify({"success": False, "error": "Already running"})
    
    main_file = cfg.get("main_file") or "main.py"
    main_cmd = cfg.get("main_command") or ""
    extract_dir = SERVERS_DIR / name / "extracted"
    main_path = extract_dir / main_file
    
    if not main_path.exists():
        return jsonify({"success": False, "error": f"{main_file} not found. Upload your files first."})
    
    log_path = SERVERS_DIR / name / "logs.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    if main_cmd:
        cmd = main_cmd.split()
    else:
        cmd = get_run_command(cfg.get("runtime", "python"), main_file)
    
    env = os.environ.copy()
    env["PORT"] = str(cfg.get("port", 8080))
    
    try:
        with open(log_path, "a") as lf:
            lf.write(f"\n{'='*50}\n[{datetime.now().isoformat()}] Starting: {' '.join(cmd)}\n{'='*50}\n")
        log_file = open(log_path, "a")
        proc = subprocess.Popen(cmd, cwd=str(extract_dir), stdout=log_file, stderr=log_file, env=env, preexec_fn=os.setsid)
        RUNNING_PROCESSES[name] = {"proc": proc, "log_file": log_file}
        cfg["status"] = "running"
        cfg["pid"] = proc.pid
        data["servers"][name] = cfg
        save_data(data)
        return jsonify({"success": True, "pid": proc.pid})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/server/<name>/stop", methods=["POST"])
@login_required
def stop_server(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False}), 404
    
    if cfg.get("owner") != session["username"] and not session.get("admin"):
        return jsonify({"success": False}), 403
    
    pid = cfg.get("pid")
    stopped = False
    
    if name in RUNNING_PROCESSES:
        entry = RUNNING_PROCESSES[name]
        proc = entry["proc"]
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            entry["log_file"].close()
        except Exception:
            pass
        del RUNNING_PROCESSES[name]
        stopped = True
    
    if pid and not stopped:
        kill_process(pid)
    
    log_path = SERVERS_DIR / name / "logs.txt"
    try:
        with open(log_path, "a") as lf:
            lf.write(f"[{datetime.now().isoformat()}] Server stopped\n")
    except Exception:
        pass
    
    cfg["status"] = "stopped"
    cfg["pid"] = None
    data["servers"][name] = cfg
    save_data(data)
    return jsonify({"success": True})

def auto_restart_stopped_servers():
    last_attempt = {}
    while True:
        time.sleep(15)
        data = load_data()
        for name, cfg in data["servers"].items():
            now = time.time()
            if name in last_attempt and now - last_attempt[name] < 60:
                continue
            pid = cfg.get("pid")
            if pid and not is_process_alive(pid):
                cfg["status"] = "stopped"
                cfg["pid"] = None
                save_data(data)
            if cfg.get("status") == "stopped":
                main_file = cfg.get("main_file") or "main.py"
                extract_dir = SERVERS_DIR / name / "extracted"
                if (extract_dir / main_file).exists():
                    last_attempt[name] = now
                    threading.Thread(target=_do_auto_reset, args=[name], daemon=True).start()

threading.Thread(target=auto_restart_stopped_servers, daemon=True).start()

@app.route("/server/<name>/logs")
@login_required
def get_logs(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"logs": "Server not found"})
    
    log_path = SERVERS_DIR / name / "logs.txt"
    if not log_path.exists():
        return jsonify({"logs": "No logs yet. Start the server to see output."})
    
    try:
        if log_path.stat().st_size > 1024 * 1024:
            with open(log_path, 'r', errors='replace') as f:
                f.seek(-50000, 2)
                content = f.read()
            content = "... (showing last 50KB) ...\n" + content
        else:
            content = log_path.read_text(errors="replace")
        lines = content.splitlines()
        if len(lines) > 200:
            lines = lines[-200:]
            content = "... (showing last 200 lines) ...\n" + "\n".join(lines)
        return jsonify({"logs": content or "No output yet."})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})
     
@app.route("/server/<name>/logs/clear", methods=["POST"])
@login_required
def clear_logs(name):
    data = load_data()
    cfg = data["servers"].get(name)
    if not cfg:
        return jsonify({"success": False})
    
    log_path = SERVERS_DIR / name / "logs.txt"
    try:
        log_path.write_text("")
    except Exception:
        pass
    return jsonify({"success": True})

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        data = load_data()
        admin_pass = data.get("settings", {}).get("admin_password", ADMIN_PASSWORD)
        if pw == admin_pass:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Wrong admin password")
    return render_template("admin_login.html", error=None)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    data = load_data()
    servers = data["servers"]
    users_raw = data["users"]
    settings = data.get("settings", {})
    site_name = settings.get("site_name", "—͞SᎻꫝᎮᎮƝ᥆ꤪꤨ 𝐂𝚘𝙳𝚎𝚡")
    
    for name, cfg in servers.items():
        pid = cfg.get("pid")
        if pid and not is_process_alive(pid):
            cfg["status"] = "stopped"
            cfg["pid"] = None
    
    running = sum(1 for v in servers.values() if v.get("status") == "running")
    total_files = 0
    for sname in servers:
        ed = SERVERS_DIR / sname / "extracted"
        if ed.exists():
            total_files += sum(1 for f in ed.rglob("*") if f.is_file())
    
    user_stats = []
    for u, u_data in users_raw.items():
        u_servers = [v for v in servers.values() if v.get("owner") == u]
        u_files = 0
        for sv in u_servers:
            ed = SERVERS_DIR / sv["name"] / "extracted"
            if ed.exists():
                u_files += sum(1 for f in ed.rglob("*") if f.is_file())
        user_stats.append({
            "username": u,
            "projects": len(u_servers),
            "running": sum(1 for sv in u_servers if sv.get("status") == "running"),
            "files": u_files,
            "joined": u_data.get("joined", "")
        })
    
    return render_template("admin.html", users=user_stats, servers=servers, settings=settings,
                           total_users=len(users_raw), total_projects=len(servers),
                           running=running, total_files=total_files,
                           theme_presets=THEME_PRESETS, site_name=site_name)

@app.route("/admin/user/<username>/files")
@admin_required
def admin_user_files(username):
    data = load_data()
    user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
    file_data = {}
    for name, cfg in user_servers.items():
        ed = SERVERS_DIR / name / "extracted"
        file_data[name] = {"config": cfg, "files": list_files(ed)}
    return render_template("admin_files.html", username=username, file_data=file_data)

@app.route("/admin/user/<username>/delete", methods=["POST"])
@admin_required
def admin_delete_user(username):
    data = load_data()
    to_delete = [k for k, v in data["servers"].items() if v.get("owner") == username]
    for name in to_delete:
        pid = data["servers"][name].get("pid")
        if pid:
            kill_process(pid)
        if name in RUNNING_PROCESSES:
            try:
                RUNNING_PROCESSES[name]["proc"].terminate()
            except Exception:
                pass
            del RUNNING_PROCESSES[name]
        if name in RESET_TIMERS:
            try:
                RESET_TIMERS[name]["timer"].cancel()
            except Exception:
                pass
            del RESET_TIMERS[name]
        shutil.rmtree(SERVERS_DIR / name, ignore_errors=True)
        del data["servers"][name]
    data["users"].pop(username, None)
    save_data(data)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/maintenance", methods=["POST"])
@admin_required
def toggle_maintenance():
    data = load_data()
    payload = request.get_json()
    data["settings"]["maintenance"] = payload.get("enabled", False)
    data["settings"]["maintenance_msg"] = payload.get("message", "Under maintenance")
    save_data(data)
    return jsonify({"success": True})

@app.route("/admin/theme", methods=["POST"])
@admin_required
def set_theme():
    data = load_data()
    payload = request.get_json()
    color = payload.get("color", "#a855f7").strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        return jsonify({"success": False, "error": "Invalid color format"}), 400
    if "settings" not in data:
        data["settings"] = {}
    data["settings"]["theme_color"] = color
    save_data(data)
    return jsonify({"success": True, "color": color})

@app.route("/admin/change-password", methods=["POST"])
@admin_required
def change_password():
    data = load_data()
    payload = request.get_json()
    ptype = payload.get("type", "admin")
    new_pass = payload.get("password", "")
    if not new_pass:
        return jsonify({"success": False, "error": "Password required"}), 400
    if ptype == "admin":
        data["settings"]["admin_password"] = new_pass
    else:
        data["settings"]["normal_password"] = new_pass
    save_data(data)
    return jsonify({"success": True})

@app.route("/admin/change-site-name", methods=["POST"])
@admin_required
def change_site_name():
    data = load_data()
    payload = request.get_json()
    new_name = payload.get("name", "")
    if new_name:
        data["settings"]["site_name"] = new_name
        save_data(data)
    return jsonify({"success": True})

@app.route("/admin/file/<project_name>/download")
@admin_required
def admin_download_file(project_name):
    file_path = request.args.get("path", "")
    if not file_path:
        abort(400)
    safe_path = (SERVERS_DIR / project_name / "extracted" / file_path).resolve()
    base = (SERVERS_DIR / project_name / "extracted").resolve()
    if not str(safe_path).startswith(str(base)) or not safe_path.exists() or safe_path.is_dir():
        abort(404)
    return send_file(safe_path, as_attachment=True, download_name=safe_path.name)

@app.route("/admin/project/<project_name>/download")
@admin_required
def admin_download_project(project_name):
    type_filter = request.args.get("type", "all")
    extract_dir = SERVERS_DIR / project_name / "extracted"
    if not extract_dir.exists():
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in extract_dir.rglob("*"):
            if not f.is_file():
                continue
            if type_filter != "all" and not f.name.endswith(type_filter):
                continue
            zf.write(f, f.relative_to(extract_dir))
    buf.seek(0)
    ext_part = type_filter.replace(".", "") if type_filter != "all" else ""
    fname = f"{project_name}{'-' + ext_part if ext_part else ''}.zip"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/zip")

@app.route("/admin/user/<username>/download")
@admin_required
def admin_download_user(username):
    type_filter = request.args.get("type", "all")
    data = load_data()
    user_servers = {k: v for k, v in data["servers"].items() if v.get("owner") == username}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in user_servers:
            extract_dir = SERVERS_DIR / name / "extracted"
            if not extract_dir.exists():
                continue
            for f in extract_dir.rglob("*"):
                if not f.is_file():
                    continue
                if type_filter != "all" and not f.name.endswith(type_filter):
                    continue
                arcname = Path(name) / f.relative_to(extract_dir)
                zf.write(f, arcname)
    buf.seek(0)
    ext_part = type_filter.replace(".", "") if type_filter != "all" else ""
    fname = f"{username}-files{'-' + ext_part if ext_part else ''}.zip"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/zip")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)