"""
Moonraker docker Timelapse - Automatic Timelapse creator for Moonraker based Printer
Created by: johann-gillieron
Based on the work of: aenima1337
License: MIT
Description: Automatically detects print status via Moonraker API and 
calculates ideal intervals for perfect 15s timelapses.
"""
VERSION = "1.0"

import requests, time, os, threading, subprocess, json, glob, re
from flask import Flask, render_template, send_from_directory, request, redirect, jsonify
from collections import deque
from pathlib import Path

app = Flask(__name__)
CONFIG_DIR = "config"
CONFIG_FILE = "printers.json"
SNAPSHOT_DIR = "snapshots"
VIDEO_DIR = "videos"
THUMB_DIR = "thumbs"
PORT = 5115
PRINTERS = {}

class Printer:
    def __init__(self, pid, ip, mode="layer"):
        self.pid = pid
        self.ip = ip
        self.mode = mode

        # Dedicate folder
        self.snapshot_dir = f"{SNAPSHOT_DIR}/{pid}"
        self.video_dir = f"{VIDEO_DIR}/{pid}"
        self.thumb_dir = f"{VIDEO_DIR}/{pid}/{THUMB_DIR}"
        # safe naming policies (no space)
        self.snapshot_dir = re.sub(r'\s+', '_', self.snapshot_dir)
        self.video_dir = re.sub(r'\s+', '_', self.video_dir)
        self.thumb_dir = re.sub(r'\s+', '_', self.thumb_dir)

        # Check if folders exists
        self.ensure_printer_dirs()

        # États internes
        self.is_printing = False
        self.last_layer = -1
        self.progress = 0
        self.time_left = "Unknown"
        self.interval = 0
        self.last_snap_time = 0
        self.last_image_ts = 0
        self.logs = deque(maxlen=10)
        self.job_filename = ""

        # Thread de monitoring
        threading.Thread(target=self.monitor_loop, daemon=True).start()

    def ensure_printer_dirs(self):
        for dir in [self.snapshot_dir, self.video_dir, self.thumb_dir]:
            os.makedirs(dir, exist_ok=True)

    def log(self, msg):
        self.logs.appendleft(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def monitor_loop(self):
        self.log("System ready.")

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
                self.time_left = int(stats["virtual_sdcard"].get("remain_time", "Unknown"))

                # Start print detection
                if state == "printing" and is_active and not self.is_printing:
                    self.is_printing = True
                    self.job_filename = filename
                    self.log("Print started.")

                    if self.mode == "time":
                        self.get_smart_interval
                        self.log(f"Smart Mode: {self.interval}s")
                    else:
                        self.interval = 0

                if self.is_printing:
                    # End print detection
                    if not is_active or state in ["complete", "standby", "error", "cancelled"] or self.progress >= 100:
                        self.is_printing = False
                        self.log(f"Print stopped (State: {state})")

                        if state == "complete" or self.progress >= 100:
                            self.log("Auto-Render...")
                            threading.Thread(target=self.render_video).start()

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

    def force_render_video(self):
        self.render_video(True)

    def render_video(self, job_manual=False):
        job_name=""
        if job_manual:
            job_name="manual_render"
        else:
            job_name=self.job_filename

        timestamp = time.strftime("%Y-%m-%d_%H-%M")
        safe_name = "".join([c for c in job_name if c.isalnum()]).rstrip() or "print"
        vid_name = f"{timestamp}_{safe_name}.mp4"

        output_file = os.path.join(self.video_dir, vid_name)
        thumb_file = os.path.join(self.thumb_dir, f"{vid_name}.jpg")

        images = sorted(glob.glob(f"{self.snapshot_dir}/*.jpg"))
        if len(images) < 2:
            self.log("Error: Not enough frames for video.")
            return

        self.log(f"Rendering {vid_name} ({len(images)} frames)...")

        try:
            subprocess.run(
                f"ffmpeg -y -framerate 30 -pattern_type glob -i '{self.snapshot_dir}/*.jpg' "
                f"-c:v libx264 -pix_fmt yuv420p -crf 23 {output_file}",
                shell=True, check=True
            )

            if images:
                subprocess.run(f"cp {images[-1]} {thumb_file}", shell=True)

            for f in images:
                os.remove(f)

            self.log("Render Success!")

        except Exception as e:
            self.log(f"Render Error: {e}")
            
    def get_smart_interval(self):
        estimated_time = 0
        try:
            url = f"http://{self.ip}/server/files/metadata?filename={self.job_filename}"
            r = requests.get(url, timeout=2)
            meta = r.json()
            estimated_time = meta['result'].get('estimated_time', 0)
        except: pass
        if estimated_time > 0:
            calc = max(5, min(estimated_time / 450, 60))
            self.interval = int(calc)
        else:
            self.interval = 15

def check_and_init_printer_config():
    path = Path(f"{CONFIG_DIR}/{CONFIG_FILE}")
    if not path.exists():
        print("Config is missing, creating a new one.")
        data = {'printers': [{'id': 'Name', 'name': 'Brand Model', 'ip': '10.10.10.90', 'mode': 'layer'}]}
        os.makedirs(CONFIG_DIR, exist_ok=True)

        with open(f"{CONFIG_DIR}/{CONFIG_FILE}", "w") as f:
            json.dump(data, f, indent=4)
    else:
        print("Config exists pass")

def load_printer_config():
    with open(f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)
        return data["printers"]

def reload_printers():
    global PRINTERS

    # Charger le fichier JSON
    check_and_init_printer_config()
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

def auto_reload_loop():
    while True:
        reload_printers()
        time.sleep(600)

def init_system():
    global PRINTERS
    # Check if the bases folders exists or create them
    for d in [SNAPSHOT_DIR, VIDEO_DIR, CONFIG_DIR]: 
        os.makedirs(d, exist_ok=True)

    check_and_init_printer_config()
    printer_configs = load_printer_config()

    for cfg in printer_configs:
        pid = cfg["id"]
        PRINTERS[pid] = Printer(
            pid=pid,
            ip=cfg["ip"],
            mode=cfg.get("mode", "layer")
        )

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
        "interval": p.interval,
        "remaining": p.time_left
    })

@app.route('/manual_render/<pid>')
def manual_render(pid):
    p = PRINTERS[pid]
    if p.is_printing:
        return "Not possible during active print", 400
    threading.Thread(target=p.force_render_video).start()
    return redirect('/')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# --- WEB INTERFACE ---
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
            "name": pid,
            "vids": vids,
            "ip": p.ip,
            "mode": p.mode
        })

    return render_template("index.html", printers=printers_data, version=VERSION)

@app.route('/save_config/<pid>', methods=['POST'])
def save_config(pid):
    p = PRINTERS[pid]

    p.ip = request.form.get('ip')
    p.mode = request.form.get('mode')

    # JSON file update
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

# --- ADMIN WEB INTERFACE ---
@app.route('/admin')
def admin_page():
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    return render_template("admin.html", printers=data["printers"])

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

@app.route('/admin/edit/<pid>')
def admin_edit(pid):
    with open( f"{CONFIG_DIR}/{CONFIG_FILE}", "r") as f:
        data = json.load(f)

    printer = next(p for p in data["printers"] if p["id"] == pid)

    return render_template("edit.html", p=printer)

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


# -- initialisations --
init_system()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
