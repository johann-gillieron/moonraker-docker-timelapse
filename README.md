# Moonraker-docker-Timelapse

**Important Requirement:**  
This tool requires a printer running [Moonraker](https://moonraker.readthedocs.io/en/latest/) to function on a Klipper printer.

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
http://[YOUR_DOCKER_HOST_IP]:5005/admin
```

Includes:

- Add a printer (ID, name, IP, mode)
- Edit printer settings
- Delete printers
- Reload configuration dynamically

### 🔄 Dynamic Printer Reloading
Modify `printers.json` or use the admin page — printers are reloaded **without restarting the container**.

### 📁 Automatic Directory Creation (Self‑Healing)
For each printer, the following directories are created automatically:

```
snapshots_<printer_id>/
videos_<printer_id>/
videos_<printer_id>/thumbs/
config/
```

If folders are missing or deleted, they are recreated automatically.

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
http://[YOUR_DOCKER_HOST_IP]:5005
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

## 📄 License and Credits

- **Author:** Johann Gillieron  
- **Based on:**  
  [Rinkhals-Timelapse](https://github.com/aenima1337/rinkhals-timelapse) by aenima1337  
- **License:** MIT  
- **Acknowledgments:**  
  Special thanks to aenima1337 for the original Rinkhals-Timelapse project.