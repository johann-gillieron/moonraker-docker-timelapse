"""
Moonraker docker Timelapse - Automatic Timelapse creator for Moonraker based Printer
Created by: johann-gillieron
Based on the work of: aenima1337
License: MIT
Description: Automatically detects print status via Moonraker API and 
calculates ideal intervals for perfect 15s timelapses.
"""

import requests, time, os, threading, subprocess, json, glob
from flask import Flask, render_template_string, send_from_directory, request, redirect, jsonify
from collections import deque

app = Flask(__name__)
CONFIG_DIR = "config"
CONFIG_FILE = "printers.json"
SNAPSHOT_DIR = "snapshots"
VIDEO_DIR = "videos"
THUMB_DIR = "thumbs"

def ensure_printer_dirs(pid):
    base_snap = f"{SNAPSHOT_DIR}/{pid}"
    base_vid = f"{VIDEO_DIR}/{pid}"
    base_thumb = f"{VIDEO_DIR}/{pid}/{THUMB_DIR}"
    base_cfg = f"{CONFIG_DIR}"

    for d in [base_snap, base_vid, base_thumb, base_cfg]:
        os.makedirs(d, exist_ok=True)

class Printer:
    def __init__(self, pid, ip, mode="layer"):
        self.pid = pid
        self.ip = ip
        self.mode = mode

        # Dossiers dédiés
        self.snapshot_dir = f"{SNAPSHOT_DIR}/{pid}"
        self.video_dir = f"{VIDEO_DIR}/{pid}"
        self.thumb_dir = f"{VIDEO_DIR}/{pid}/{THUMB_DIR}"

        ensure_printer_dirs(pid)


        for d in [self.snapshot_dir, self.video_dir, self.thumb_dir]:
            os.makedirs(d, exist_ok=True)

        # États internes
        self.is_printing = False
        self.last_layer = -1
        self.progress = 0
        self.interval = 0
        self.last_snap_time = 0
        self.last_image_ts = 0
        self.logs = deque(maxlen=10)

        # Thread de monitoring
        threading.Thread(target=self.monitor_loop, daemon=True).start()

    def log(self, msg):
        self.logs.appendleft(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def monitor_loop(self):
        self.log("System ready.")
        job_filename = ""

        while True:
            try:
                r = requests.get(
                    f"http://{self.ip}:7125/printer/objects/query?virtual_sdcard&print_stats",
                    timeout=3
                ).json()

                stats = r["result"]["status"]
                state = stats["print_stats"]["state"]
                filename = stats["print_stats"]["filename"]
                is_active = stats["virtual_sdcard"].get("is_active", False)
                current_layer = stats["virtual_sdcard"].get("current_layer", 0)
                self.progress = int(stats["virtual_sdcard"].get("progress", 0) * 100)

                # Détection début impression
                if state == "printing" and is_active and not self.is_printing:
                    self.is_printing = True
                    job_filename = filename
                    self.log("Print started.")

                    if self.mode == "time":
                        self.interval = get_smart_interval(self.ip, filename)
                        self.log(f"Smart Mode: {self.interval}s")
                    else:
                        self.interval = 0

                # Fin impression
                if self.is_printing:
                    if not is_active or state in ["complete", "standby", "error", "cancelled"] or self.progress >= 100:
                        self.is_printing = False
                        self.log(f"Print stopped (State: {state})")

                        if state == "complete" or self.progress >= 100:
                            self.log("Auto-Render...")
                            threading.Thread(target=render_video, args=(self, job_filename)).start()

                        self.last_layer = -1
                        continue

                    # Capture
                    take_snap = False
                    if self.mode == "layer":
                        if current_layer > 0 and current_layer != self.last_layer:
                            take_snap = True
                            self.last_layer = current_layer

                    elif self.mode == "time":
                        now = time.time()
                        if (now - self.last_snap_time) > self.interval:
                            take_snap = True
                            self.last_snap_time = now

                    if take_snap:
                        ts_idx = int(time.time() * 10)
                        img_data = requests.get(
                            f"http://{self.ip}/webcam/?action=snapshot",
                            timeout=5
                        ).content

                        with open(f"{self.snapshot_dir}/frame_{ts_idx}.jpg", "wb") as f:
                            f.write(img_data)

                        self.last_image_ts = time.time()

            except Exception as e:
                self.log(f"Error: {e}")

            time.sleep(2)

for d in [SNAPSHOT_DIR, VIDEO_DIR, THUMB_DIR]: 
    os.makedirs(d, exist_ok=True)

def load_printer_config():
    with open(f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)
        return data["printers"]

LOG_STACK = deque(maxlen=10)
printer_configs = load_printer_config()

PRINTERS = {}

for cfg in printer_configs:
    pid = cfg["id"]
    PRINTERS[pid] = Printer(
        pid=pid,
        ip=cfg["ip"],
        mode=cfg.get("mode", "layer")
    )

def render_video(printer, job_name="manual_render"):
    timestamp = time.strftime("%Y-%m-%d_%H-%M")
    safe_name = "".join([c for c in job_name if c.isalnum()]).rstrip() or "print"
    vid_name = f"{timestamp}_{safe_name}.mp4"

    output_file = os.path.join(printer.video_dir, vid_name)
    thumb_file = os.path.join(printer.thumb_dir, f"{vid_name}.jpg")

    images = sorted(glob.glob(f"{printer.snapshot_dir}/*.jpg"))
    if len(images) < 2:
        printer.log("Error: Not enough frames for video.")
        return

    printer.log(f"Rendering {vid_name} ({len(images)} frames)...")

    try:
        subprocess.run(
            f"ffmpeg -y -framerate 30 -pattern_type glob -i '{printer.snapshot_dir}/*.jpg' "
            f"-c:v libx264 -pix_fmt yuv420p -crf 23 {output_file}",
            shell=True, check=True
        )

        if images:
            subprocess.run(f"cp {images[-1]} {thumb_file}", shell=True)

        for f in images:
            os.remove(f)

        printer.log("Render Success!")

    except Exception as e:
        printer.log(f"Render Error: {e}")

def get_smart_interval(ip, filename):
    try:
        url = f"http://{ip}/server/files/metadata?filename={filename}"
        r = requests.get(url, timeout=2)
        meta = r.json()
        estimated_time = meta['result'].get('estimated_time', 0)
        if estimated_time > 0:
            calc = max(5, min(estimated_time / 450, 60))
            return int(calc)
    except: pass
    return 15

def reload_printers():
    global PRINTERS

    # Charger le fichier JSON
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    new_list = {p["id"]: p for p in data["printers"]}

    # Supprimer les imprimantes retirées du fichier
    for pid in list(PRINTERS.keys()):
        if pid not in new_list:
            print(f"[Cluster] Removing printer {pid}")
            del PRINTERS[pid]

    # Ajouter / mettre à jour les imprimantes
    for pid, cfg in new_list.items():
        if pid not in PRINTERS:
            print(f"[Cluster] Adding printer {pid}")
            PRINTERS[pid] = Printer(
                pid=pid,
                ip=cfg["ip"],
                mode=cfg.get("mode", "layer")
            )
        else:
            # Mise à jour des paramètres
            p = PRINTERS[pid]
            p.ip = cfg["ip"]
            p.mode = cfg.get("mode", "layer")

        # Vérifier / créer les dossiers
        ensure_printer_dirs(pid)

def auto_reload_loop():
    while True:
        reload_printers()
        time.sleep(600)

#threading.Thread(target=auto_reload_loop, daemon=True).start()

# --- API ENDPOINTS ---
@app.route('/status/<pid>')
def status_api(pid):
    p = PRINTERS[pid]
    video_count = len([f for f in os.listdir(p.video_dir) if f.endswith('.mp4')])
    return jsonify({
        "is_printing": p.is_printing,
        "progress": p.progress,
        "logs": list(p.logs),
        "img_ts": p.last_image_ts,
        "video_count": video_count,
        "mode": p.mode,
        "interval": p.interval
    })

@app.route('/manual_render/<pid>')
def manual_render(pid):
    p = PRINTERS[pid]
    if p.is_printing:
        return "Not possible during active print", 400
    threading.Thread(target=render_video, args=(p, "manual_job")).start()
    return redirect('/')

# --- WEB INTERFACE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Moonraker Timelapse Cluster</title>

    <style>
        :root { --bg: #0f1116; --card: #1a1d23; --border: #2d3748; --accent: #3b82f6; --text: #e2e8f0; --danger: #ef4444; }
        body { background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; margin: 0; padding: 20px; }
        .layout { display: grid; grid-template-columns: 280px 1fr; gap: 30px; max-width: 1400px; margin: 0 auto; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); }
        .header-title { color: var(--accent); font-weight: 900; font-size: 20px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        .status-header { display: flex; justify-content: space-between; font-size: 11px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase; color: #64748b; }
        .rec { color: var(--danger); animation: blink 1.5s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
        .img-container { width: 100%; aspect-ratio: 16/9; background: #000; border-radius: 8px; border: 1px solid var(--border); overflow: hidden; margin-bottom: 15px; }
        .preview-img { width: 100%; height: 100%; object-fit: cover; display: block; }
        .info-row { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 5px; color: #94a3b8; }
        .val { color: white; font-weight: bold; }
        .progress-bar { background: #090b10; height: 6px; border-radius: 4px; margin: 5px 0 15px 0; overflow: hidden; }
        .progress-fill { background: var(--accent); height: 100%; width: 0%; transition: width 0.5s ease; }
        .log-area { background: #090b10; border-radius: 6px; padding: 8px; font-family: monospace; font-size: 10px; height: 120px; overflow-y: auto; color: #94a3b8; border: 1px solid #1e293b; margin-bottom: 15px; }
        .settings-form { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid var(--border); padding-top: 15px; }
        .input-group { display: flex; flex-direction: column; gap: 4px; }
        .label { font-size: 10px; font-weight: bold; color: #64748b; text-transform: uppercase; }
        input, select { background: #0f1116; border: 1px solid var(--border); color: white; padding: 8px; border-radius: 4px; font-size: 12px; }
        .btn { background: var(--accent); color: white; border: none; padding: 10px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 11px; text-transform: uppercase; transition: 0.2s; }
        .btn-danger { background: #334155; margin-top: 5px; color: #cbd5e1; }
        .btn-danger:hover { background: var(--danger); color: white; }
        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; }
        .vid-item { background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; cursor: pointer; position: relative; transition: 0.2s; }
        .vid-item:hover { transform: translateY(-3px); border-color: var(--accent); }
        .vid-thumb { width: 100%; aspect-ratio: 16/9; object-fit: cover; opacity: 0.8; }
        .vid-name { padding: 10px; font-size: 10px; color: #cbd5e1; }
        .del-btn { position: absolute; top: 5px; right: 5px; background: rgba(220, 38, 38, 0.9); color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 9px; opacity: 0; }
        .vid-item:hover .del-btn { opacity: 1; }
        #modal { position: fixed; inset: 0; background: rgba(0,0,0,0.95); display: none; align-items: center; justify-content: center; z-index: 1000; padding: 20px; backdrop-filter: blur(5px); }
        .modal-inner { width: 100%; max-width: 900px; display: flex; flex-direction: column; gap: 15px; }
        video { width: 100%; border-radius: 8px; background: #000; }
        /* --- Tabs --- */
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn {
            background: var(--card); border: 1px solid var(--border);
            padding: 8px 14px; border-radius: 6px; cursor: pointer;
            font-size: 12px; color: var(--text); transition: 0.2s;
        }
        .tab-btn.active { background: var(--accent); border-color: var(--accent); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>

<body>

    <!-- ===================== PRINTER TABS ===================== -->
    <div class="tabs">
        {% for p in printers %}
            <div class="tab-btn {% if loop.first %}active{% endif %}"
                 onclick="switchTab('{{p.id}}')" id="tab-{{p.id}}">
                {{p.name}}
            </div>
        {% endfor %}
    </div>

    <!-- ===================== DASHBOARD PER PRINTER ===================== -->
    {% for p in printers %}
    <div class="tab-content {% if loop.first %}active{% endif %}" id="content-{{p.id}}">

        <div class="layout">

            <!-- ===================== SIDEBAR ===================== -->
            <div class="sidebar">
                <div class="header-title">{{p.name}}</div>

                <div class="card">

                    <div class="status-header">
                        <span>Status</span>
                        <span id="status-text-{{p.id}}">● STANDBY</span>
                    </div>

                    <div class="img-container">
                        <img id="cam-img-{{p.id}}" src="/last_snap/{{p.id}}" class="preview-img">
                    </div>

                    <div class="info-row">
                        <span>Progress</span>
                        <span class="val" id="progress-text-{{p.id}}">0%</span>
                    </div>

                    <div class="progress-bar">
                        <div id="progress-fill-{{p.id}}" class="progress-fill"></div>
                    </div>

                    <div id="smart-info-{{p.id}}" class="info-row"
                         style="margin-bottom: 10px; color: #3b82f6; display: none;">
                        <span>Smart Interval</span>
                        <span class="val" id="interval-val-{{p.id}}">0s</span>
                    </div>

                    <div class="log-area" id="log-box-{{p.id}}"></div>

                    <!-- ===================== SETTINGS ===================== -->
                    <form action="/save_config/{{p.id}}" method="POST" class="settings-form">
                        <div class="input-group">
                            <label class="label">Printer IP</label>
                            <input name="ip" value="{{p.ip}}">
                        </div>

                        <div class="input-group">
                            <label class="label">Capture Mode</label>
                            <select name="mode">
                                <option value="layer" {% if p.mode == 'layer' %}selected{% endif %}>Layer</option>
                                <option value="time" {% if p.mode == 'time' %}selected{% endif %}>Smart Time</option>
                            </select>
                        </div>

                        <button class="btn">SAVE SETTINGS</button>
                        <a href="/manual_render/{{p.id}}" class="btn btn-danger">FORCE RENDER</a>
                    </form>

                </div>
            </div>

            <!-- ===================== CLIPS ===================== -->
            <div class="main">
                <div style="font-size: 12px; font-weight: 900; color: #64748b; margin-bottom: 15px; text-transform: uppercase;">
                    Clips
                </div>

                <div class="gallery">
                    {% for vid in p.vids %}
                    <div class="vid-item" onclick="openVid('{{p.id}}','{{vid}}')">
                        <img src="/thumb/{{p.id}}/{{vid}}.jpg" class="vid-thumb">
                        <div class="vid-name">{{vid}}</div>
                        <a href="/delete/{{p.id}}/{{vid}}" class="del-btn"
                           onclick="event.stopPropagation(); return confirm('Delete?')">DEL</a>
                    </div>
                    {% endfor %}
                </div>
            </div>

        </div>
    </div>
    {% endfor %}

    <!-- ===================== MODAL VIDEO ===================== -->
    <div id="modal" onclick="closeVid()">
        <div class="modal-inner" onclick="event.stopPropagation()">
            <video id="player" controls></video>
            <div style="display:flex; justify-content: flex-end; gap:10px;">
                <button class="btn" onclick="closeVid()">CLOSE</button>
                <a id="dl-btn" href="#" download class="btn" style="text-decoration:none">DOWNLOAD</a>
            </div>
        </div>
    </div>

    <!-- ===================== JAVASCRIPT ===================== -->
    <script>

        function switchTab(id) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            document.getElementById('tab-' + id).classList.add('active');
            document.getElementById('content-' + id).classList.add('active');
        }

        function updateStatus(pid) {
            fetch('/status/' + pid)
                .then(r => r.json())
                .then(data => {

                    const s = document.getElementById('status-text-' + pid);
                    s.innerHTML = data.is_printing
                        ? '<span class="rec">● RECORDING</span>'
                        : '● STANDBY';

                    document.getElementById('progress-text-' + pid).innerText = data.progress + '%';
                    document.getElementById('progress-fill-' + pid).style.width = data.progress + '%';

                    const smart = document.getElementById('smart-info-' + pid);
                    smart.style.display = (data.is_printing && data.mode === 'time') ? 'flex' : 'none';

                    if (data.interval)
                        document.getElementById('interval-val-' + pid).innerText = data.interval + 's';

                    document.getElementById('log-box-' + pid).innerHTML =
                        data.logs.map(l => `<div style="border-bottom:1px solid #1e293b">${l}</div>`).join('');

                    document.getElementById('cam-img-' + pid).src =
                        '/last_snap/' + pid + '?t=' + data.img_ts;
                });
        }

        // Mise à jour pour chaque imprimante
        {% for p in printers %}
            setInterval(() => updateStatus('{{p.id}}'), 2000);
        {% endfor %}

        function openVid(pid, file) {
            document.getElementById('player').src = '/video_file/' + pid + '/' + file;
            document.getElementById('dl-btn').href = '/video_file/' + pid + '/' + file;
            document.getElementById('modal').style.display = 'flex';
            document.getElementById('player').play();
        }

        function closeVid() {
            document.getElementById('modal').style.display = 'none';
            document.getElementById('player').pause();
        }

    </script>
    <div style="text-align: center; padding: 20px; font-size: 10px; color: #64748b;">
        <strong>Moonraker Timelapse v0.5 | Created by johann-gillieron</strong> | 
        <a href="https://github.com/johann-gillieron/moonraker-docker-timelapse" target="_blank" style="color: #64748b;">GitHub</a>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    printers_data = []

    for pid, p in PRINTERS.items():
        vids = sorted(
            [f for f in os.listdir(p.video_dir) if f.endswith('.mp4')],
            reverse=True
        )

        printers_data.append({
            "id": pid,
            "name": pid,  # ou p.name si tu l’ajoutes dans printers.json
            "vids": vids,
            "ip": p.ip,
            "mode": p.mode
        })

    return render_template_string(HTML_TEMPLATE, printers=printers_data)

@app.route('/save_config/<pid>', methods=['POST'])
def save_config(pid):
    p = PRINTERS[pid]

    p.ip = request.form.get('ip')
    p.mode = request.form.get('mode')

    # Mise à jour du fichier JSON
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    for printer in data["printers"]:
        if printer["id"] == pid:
            printer["ip"] = p.ip
            printer["mode"] = p.mode

    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "w") as f:
        json.dump(data, f, indent=4)

    return redirect('/')

@app.route('/last_snap/<pid>')
def last_snap(pid):
    p = PRINTERS[pid]
    snaps = sorted(glob.glob(f"{p.snapshot_dir}/*.jpg"))

    if snaps:
        latest = max(snaps, key=os.path.getmtime)
        return send_from_directory(p.snapshot_dir, os.path.basename(latest))

    return redirect("https://via.placeholder.com/320x180/1a1d23/3b82f6?text=Ready")

@app.route('/thumb/<pid>/<path:filename>')
def thumb(pid, filename):
    p = PRINTERS[pid]
    return send_from_directory(p.thumb_dir, filename)

@app.route('/video_file/<pid>/<path:filename>')
def video_file(pid, filename):
    p = PRINTERS[pid]
    return send_from_directory(p.video_dir, filename)

@app.route('/delete/<pid>/<path:filename>')
def delete(pid, filename):
    p = PRINTERS[pid]
    try:
        os.remove(os.path.join(p.video_dir, filename))
        os.remove(os.path.join(p.thumb_dir, filename + ".jpg"))
    except:
        pass

    return redirect('/')

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Printer Administration</title>
    <style>
        body { background:#0f1116; color:#e2e8f0; font-family:sans-serif; padding:20px; }
        .card { background:#1a1d23; padding:20px; border-radius:10px; border:1px solid #2d3748; margin-bottom:20px; }
        input, select { width:100%; padding:8px; background:#0f1116; border:1px solid #2d3748; color:white; border-radius:4px; }
        .btn { background:#3b82f6; padding:10px; border:none; border-radius:4px; color:white; cursor:pointer; }
        .btn-danger { background:#ef4444; }
        table { width:100%; border-collapse:collapse; margin-top:20px; }
        th, td { padding:10px; border-bottom:1px solid #2d3748; }
        a { color:#3b82f6; text-decoration:none; }
    </style>
</head>
<body>

<h1>Printer Administration</h1>

<div class="card">
    <h2>Add Printer</h2>
    <form action="/admin/add" method="POST">
        <label>ID</label>
        <input name="id" required>

        <label>Name</label>
        <input name="name" required>

        <label>IP</label>
        <input name="ip" required>

        <label>Mode</label>
        <select name="mode">
            <option value="layer">Layer</option>
            <option value="time">Smart Time</option>
        </select>

        <button class="btn" style="margin-top:10px;">Add Printer</button>
    </form>
</div>

<div class="card">
    <h2>Existing Printers</h2>
    <table>
        <tr><th>ID</th><th>Name</th><th>IP</th><th>Mode</th><th>Actions</th></tr>
        {% for p in printers %}
        <tr>
            <td>{{p.id}}</td>
            <td>{{p.name}}</td>
            <td>{{p.ip}}</td>
            <td>{{p.mode}}</td>
            <td>
                <a href="/admin/edit/{{p.id}}">Edit</a> |
                <a href="/admin/delete/{{p.id}}" onclick="return confirm('Delete printer?')">Delete</a>
            </td>
        </tr>
        {% endfor %}
    </table>
    <a href="/admin/reload" class="btn">Reload Printers</a>
</div>
</body>
</html>
"""

@app.route('/admin')
def admin_page():
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    return render_template_string(ADMIN_TEMPLATE, printers=data["printers"])

@app.route('/admin/add', methods=['POST'])
def admin_add():
    new_printer = {
        "id": request.form["id"],
        "name": request.form["name"],
        "ip": request.form["ip"],
        "mode": request.form["mode"]
    }

    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    data["printers"].append(new_printer)

    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "w") as f:
        json.dump(data, f, indent=4)

    return redirect('/admin')

@app.route('/admin/delete/<pid>')
def admin_delete(pid):
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    data["printers"] = [p for p in data["printers"] if p["id"] != pid]

    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "w") as f:
        json.dump(data, f, indent=4)

    return redirect('/admin')

EDIT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Edit Printer</title>
    <style>
        body { background:#0f1116; color:#e2e8f0; font-family:sans-serif; padding:20px; }
        .card { background:#1a1d23; padding:20px; border-radius:10px; border:1px solid #2d3748; }
        input, select { width:100%; padding:8px; background:#0f1116; border:1px solid #2d3748; color:white; border-radius:4px; }
        .btn { background:#3b82f6; padding:10px; border:none; border-radius:4px; color:white; cursor:pointer; }
    </style>
</head>
<body>

<h1>Edit Printer {{p.id}}</h1>

<div class="card">
    <form action="/admin/edit/{{p.id}}" method="POST">
        <label>Name</label>
        <input name="name" value="{{p.name}}">

        <label>IP</label>
        <input name="ip" value="{{p.ip}}">

        <label>Mode</label>
        <select name="mode">
            <option value="layer" {% if p.mode=='layer' %}selected{% endif %}>Layer</option>
            <option value="time" {% if p.mode=='time' %}selected{% endif %}>Smart Time</option>
        </select>

        <button class="btn" style="margin-top:10px;">Save</button>
    </form>
</div>

</body>
</html>
"""

@app.route('/admin/edit/<pid>')
def admin_edit(pid):
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    printer = next(p for p in data["printers"] if p["id"] == pid)

    return render_template_string(EDIT_TEMPLATE, p=printer)

@app.route('/admin/edit/<pid>', methods=['POST'])
def admin_edit_save(pid):
    with open(f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    for p in data["printers"]:
        if p["id"] == pid:
            p["name"] = request.form["name"]
            p["ip"] = request.form["ip"]
            p["mode"] = request.form["mode"]

    with open(f"{CONFIG_DIR}/{CONFIG_FILE}", "w") as f:
        json.dump(data, f, indent=4)

    return redirect('/admin')

@app.route('/admin/reload')
def admin_reload():
    reload_printers()
    return redirect('/admin')

if __name__ == '__main__':
    for p in PRINTERS.values():
        # Le thread est déjà lancé dans Printer.__init__
        pass

    app.run(host='0.0.0.0', port=5005)
