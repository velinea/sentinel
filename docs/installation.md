# Installation

This guide describes how to install Sentinel on a Debian-based system using two lightweight services:

- **Sentinel** – the main application
- **Sentinel Inference** – the OpenVINO inference server

The installation described here matches the development environment and is recommended for new installations.

---

# Tested environment

Sentinel has been developed and tested with:

| Component | Version |
|----------|---------|
| Proxmox VE | 9 |
| Debian | 13 (LXC) |
| Home Assistant | Home Assistant OS |
| Python | 3.13 |
| OpenVINO | Current Debian package |
| Hardware | Intel N100 Mini PC |

Although other Linux distributions should work, Debian is the primary development platform.

---

# Recommended architecture

```
                    Proxmox

        +----------------------------+
        | Home Assistant OS          |
        +-------------+--------------+
                      |
            Snapshot API
                      |
        +-------------v--------------+
        | Debian LXC                |
        | sentinel                  |
        |---------------------------|
        | sentinel                  |
        | sentinel-http             |
        +-------------+-------------+
                      |
                  REST API
                      |
        +-------------v-------------+
        | Debian LXC               |
        | sentinel-inference       |
        |--------------------------|
        | OpenVINO                 |
        | YOLO                     |
        | inference server         |
        +--------------------------+
```

Separating inference from the main application keeps the system modular and allows the inference backend to evolve independently.

---

# Prerequisites

Before installing Sentinel, ensure that:

- Home Assistant is operational.
- One or more camera entities provide snapshots.
- The Home Assistant REST API is accessible.
- Python 3.13 is installed.
- Git is available.

---

# Clone the repository

```bash
git clone https://github.com/velinea/sentinel.git
cd sentinel
```

---

# Python virtual environment

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Installing Sentinel Inference

Create a second Debian LXC (recommended).

Install OpenVINO according to Intel's instructions.

Clone the Sentinel repository.

Install Python dependencies.

Start the inference server:

```bash
python sentinel-inference.py
```

Verify that the server is listening on:

```
http://<inference-server>:8000
```

---

# Configure Sentinel

Copy the example configuration:

```bash
cp config-example.yaml config.yaml
```

Edit the configuration:

```yaml
home_assistant:
  url: http://homeassistant:8123
  token: YOUR_LONG_LIVED_ACCESS_TOKEN

inference:
  url: http://sentinel-inference:8000
```

Configure your cameras and interesting objects.

---

# Run Sentinel

Start the detector:

```bash
python sentinel.py
```

Start the HTTP service:

```bash
python sentinel-http.py
```

---

# Configure systemd services

Sentinel is intended to run as system services.

Typical installation:

```
sentinel.service
sentinel-http.service
sentinel-inference.service
```

Enable automatic startup:

```bash
sudo systemctl enable sentinel
sudo systemctl enable sentinel-http
sudo systemctl enable sentinel-inference
```

Start the services:

```bash
sudo systemctl start sentinel
sudo systemctl start sentinel-http
sudo systemctl start sentinel-inference
```

---

# Home Assistant

Add Generic Camera entities pointing to Sentinel's HTTP server.

Each configured camera exposes the latest interesting detection.

These entities can be used directly in Lovelace dashboards and automations.

---

# Verify operation

When Sentinel starts correctly you should observe:

- cameras discovered
- snapshots being polled
- successful inference requests
- detections logged
- snapshots saved
- latest images available through the HTTP server

---

# Next steps

Continue with:

- Configuration
- Home Assistant integration
- Troubleshooting