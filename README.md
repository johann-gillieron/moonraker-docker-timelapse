# Moonraker-docker-Timelapse

**Important Requirement:**  
This tool requires a printer running [Moonraker](https://moonraker.readthedocs.io/en/latest/) to work with a Klipper printer.

**Based on:**  
[Rinkhals-Timelapse by aenima1337](https://github.com/aenima1337/rinkhals-timelapse).  
Special thanks for proving that an external self‑hosted service is viable for Klipper printers with low computing power.

---

Moonraker-docker-Timelapse is a lightweight Docker-based tool that automatically creates timelapse videos of your 3D prints.  
It passively monitors your printer via the Moonraker API — **no slicer plugins, no G-code macros, no TIMELAPSE_TAKE_FRAME required**.

This revised version adds **full multi‑printer support**, making it ideal for users with multiple Klipper printers or print farms.

---

## ✨ Features

### 🎥 Timelapse Capture Modes
- **Smart Time Mode**  
  Automatically calculates the optimal capture interval based on estimated print time to produce a consistent ~15s video — perfect for social media.

- **Layer Mode**  
  Captures a frame at every detected layer change.

### 🧠 Intelligent & Independent
- **G-Code Independent**  
  No slicer modifications required. Everything is detected via Moonraker.

- **Zero Printer Load**  
  All processing happens on your Docker host (Pi/PC). No stress on the printer MCU.

### 🖥️ Web Interface
- **Stable UI**  
  Real-time status, logs, and image previews without flickering or layout shifts.

- **Manual Render**  
  Generate a timelapse manually from existing snapshots if a print was interrupted.

### 🏭 Multi‑Printer Cluster Support
- **Multiple Printers**  
  Monitor and generate timelapses for several printers simultaneously.

- **Tabbed Dashboard**  
  Each printer gets its own tab with independent status, logs, snapshots, and video gallery.

### 🔧 Administration Interface
Accessible at:

```
http://[YOUR_DOCKER_HOST_IP]:5115/admin
```

Includes:

- Add a printer (name, model, IP, mode)
- Edit printer settings
- Delete printers
- Reload configuration dynamically

### 🔄 Dynamic Printer Reloading
Modify `printers.json` or use the admin page — printers are reloaded **without restarting the container**.

## 📁 Automatic Directory Creation (Self‑Healing)

Moonraker‑docker‑Timelapse automatically creates and maintains a clean directory structure for each printer.  
If any folder is missing, corrupted, or deleted manually, the service will **recreate it on startup or during dynamic reload**, ensuring the system remains stable and functional.

### Directory structure per printer

```
snapshots/<printer_id>/
videos/<printer_id>/
videos/<printer_id>/thumbs/
config/
```

### 🔒 Persistence in Docker

Inside a Docker container, files are **not persistent** unless you explicitly mount them.  
To ensure your snapshots and videos survive container restarts, you must map the directories to existing host folders:

```yaml
volumes:
  - ./config:/app/config
  - ./snapshots:/app/snapshots
  - ./videos:/app/videos
```

This makes the automatically created folders **persistent**, because they are stored on your host machine rather than inside the ephemeral container filesystem.


### 🧩 Multi‑Architecture Support
Compatible with:

- x86_64 (PC)
- ARM64 (Raspberry Pi)

---

## 📦 Setup with Docker Compose

1. Create a directory for the project.
2. Create a `docker-compose.yml` file:

```yaml
services:
  moonraker-docker-timelapse:
    image: ghcr.io/johann-gillieron/moonraker-docker-timelapse:latest
    container_name: moonraker-docker-timelapse
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./config:/app/config
      - ./snapshots:/app/snapshots
      - ./videos:/app/videos
```

3. Start the container:

```bash
docker compose up -d
```

4. Access the interface:

```
http://[YOUR_DOCKER_HOST_IP]:5115
```

5. Configure your printers via the **Admin Page** or by editing `printers.json`.

---

## 🛠️ How It Works

The application communicates with the Moonraker API to track print progress.

### Layer Mode
Triggers a snapshot whenever `current_layer` increases.

### Smart Time Mode
Fetches metadata from the G-code file:

- Reads `estimated_time`
- Divides by a target frame count
- Produces a consistent timelapse duration

---

## 🛠️ Troubleshooting: Layer Mode Not Working

If **Layer Mode** does not trigger or inconsistent trigger the snapshots, the issue is usually related to **slicer G-code comments**.  
Moonraker relies on specific comments inside the G-code file to detect layer changes.  
Some slicers do **not** include these comments by default.

To fix this, you must manually add layer‑change comments in your slicer’s machine G-code settings.

### 🧩 Example: OrcaSlicer

Go to:

```
Printer Settings → Machine G-code
```

Then add the following:

#### **G-code before layer change**
```gcode
; BEFORE_LAYER_CHANGE [layer_num] @ [layer_z]mm
```

#### **G-code after layer change**
```gcode
; AFTER_LAYER_CHANGE [layer_num] @ [layer_z]mm
```

### ✔️ Why this is required

Moonraker parses the G-code file and uses these comments to update:

- `current_layer`
- `layer_z`
- layer‑based progress tracking

Without these comments, Moonraker cannot detect layer changes, and **Layer Mode will not capture frames**.

### 💡 Tip

If you use another slicer (PrusaSlicer, SuperSlicer, Cura, etc.), ensure it also inserts layer‑change comments.  
Most slicers support this, but the syntax may differ.

---

## 📄 License and Credits

- **Author:** Johann Gillieron  
- **Based on:** [Rinkhals-Timelapse](https://github.com/aenima1337/rinkhals-timelapse) by aenima1337  
- **License:** MIT  
- **Acknowledgments:**  Special thanks to aenima1337 for the original Rinkhals-Timelapse project.