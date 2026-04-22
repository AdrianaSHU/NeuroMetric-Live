# NeuroMetric-Live: A Privacy-First Multimodal BCI for the Edge

NeuroMetric-Live is a fully localised, privacy-first Fog-Computing architecture designed to transition affective-computing workloads from the cloud to the edge. Operating on a 16 GB Raspberry Pi 5, the system performs continuous on-device correlation of facial landmarks and brainwave telemetry.

By merging a quantised MobileNet facial-recognition pipeline with an 8-channel, 250Hz Electroencephalography (EEG) 1D-Convolutional Neural Network (CNN), the system leverages a dynamic Softmax algorithm to detect affective dissonance (social masking) in real time.

## Primary Use Case: Overcoming "Social Masking"

Standard optical emotion-recognition systems are easily fooled by "social masking" (when a patient intentionally forces a smile to hide anxiety or distress.) 

NeuroMetric-Live eliminates this clinical blind spot through multimodal fusion:

* **The Problem:** Single-modality cameras log forced smiles as "Happy", completely missing the underlying distress.
* **The Solution:** The system synchronises an HD video feed with live 8-channel EEG brainwave telemetry.
* **The "Dissonance Gate":** If a patient fakes a smile, the algorithm mathematically detects the conflict between the visual face and the high-arousal neural data. 
* **The "Neural Truth":** The system instantly overrides the deceptive camera feed and reveals the hidden distress to the clinician.
* **Edge Privacy:** Everything runs 100% offline on a local Raspberry Pi 5. No data is ever sent to the cloud; authorised administrators securely download the session logs directly from the device via an encrypted tunnel.

## System Architecture
* **Hardware Node:** Raspberry Pi 5 (16 GB) with active cooling.
* **Sensor Layer:** OpenBCI Ultracortex Mark IV (8-channel, Fp1/Fp2 removed to eliminate ocular artefacts) and HD Webcam.
* **Backend:** Python, FastAPI (Asynchronous ASGI runtime).
* **AI Frameworks:** PyTorch (EEG classification), TensorFlow Lite & MediaPipe (Optical classification).
* **Security:** AES-256 encryption, stateless JSON Web Token (JWT) Zero-Trust architecture, and offline MariaDB storage.

## Project Structure

```text
NeuroMetric-Live/
├── .venv/                      # Python virtual environment
├── app/                        # Main FastAPI application package
│   ├── core/                   # Security, config, database, and schemas
│   ├── engine/                 # ML processing (EEG, Face, Multimodal Fusion)
│   ├── sensors/                # Hardware interfacing (Camera, OpenBCI)
│   ├── static/                 # CSS, JavaScript, and static images
│   ├── templates/              # HTML Jinja2 templates (Dashboard, Login)
│   └── main.py                 # FastAPI application entry point
├── certs/                      # SSL certificates (cert.pem, key.pem)
├── Jupyter_notebooks/          # Training scripts for PyTorch and TFLite models
├── logs/                       # Append-on-the-fly CSV telemetry output files
├── models/                     # Compiled weights (.pth and .tflite)
├── .env                        # Environment variables (Database credentials, ports)
├── create_admin.py             # Script to generate the initial superuser account
├── reset_admin.py              # Script to force-reset admin credentials
├── requirements.txt            # Python package dependencies
└── secret.key                  # Cryptographic key for JWT generation
```

## Installation and Prerequisites
Hardware Requirements: Ensure the OpenBCI Cyton dongle is connected to the Raspberry Pi USB port (typically mounted at /dev/ttyUSB0) and the webcam is connected.

Environment Setup: Navigate to the project directory and create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Database Initialisation: 
Ensure MariaDB is installed and running on the Raspberry Pi. The system will automatically construct the required tables upon the first boot. Run the administration script to create your secure login:

```bash
python3 create_admin.py
```

## Secure Execution Instructions
To maintain strict data sovereignty and comply with the system's privacy requirements, the FastAPI dashboard is not exposed to the open web. It must be accessed via a secure SSH tunnel.

### 1. Establish the Secure Tunnel
From your remote laptop or PC terminal, open an encrypted tunnel to the Raspberry Pi:

```bash
ssh -L 8000:localhost:8000 pi@devbci.local
(Accept the security warning and enter the Raspberry Pi password when prompted. Leave this terminal open).
```

### 2. Launch the Edge Backend
On the Raspberry Pi (either directly or through the SSH terminal), navigate to the project directory, activate the environment, and start the application:

```bash
cd ~/Desktop/FastAPI
source .venv/bin/activate
python3 -m app.main
```

The terminal will confirm hardware readiness and display [Hardware] OpenBCI Cyton Board Ready and Streaming.

### 3. Access the Dashboard
Open a web browser on your remote laptop/PC and navigate to:

```text
https://localhost:8000
```

Log in using your authorised administrator credentials to begin monitoring the multimodal telemetry.

Data Logging and Telemetry
Once an active subject is selected via the dashboard, the system generates a user-specific CSV file within the /logs/ directory. High-frequency telemetry is appended to the disk every 2.0 seconds to prevent data loss in the event of hardware power failure. Authorised users can download these logs directly from the dashboard interface.

* **Environment Variables:** For security, credentials are not included in this repository. 