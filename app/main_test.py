import uvicorn
import threading
import time
import random
import os
import csv
import io
import secrets
import signal
import sys
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from contextlib import asynccontextmanager

# Import Core
from app.core import database, security

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()

# --- SECURITY CONFIGURATION ---
security_auth = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security_auth)):
    correct_user = os.getenv("ADMIN_USER")
    correct_pass = os.getenv("ADMIN_PASS")

    if not correct_user or not correct_pass:
        raise HTTPException(status_code=500, detail="Security Config Missing")

    is_user_ok = secrets.compare_digest(credentials.username, correct_user)
    is_pass_ok = secrets.compare_digest(credentials.password, correct_pass)
    
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- MOCK SENSORS ---
class MockEEGSensor:
    def __init__(self):
        self.latest_emotion = "Waiting..."
        self.latest_conf = 0.0
        self.running = False
    def start(self): self.running = True
    def stop(self): self.running = False
    def process_data(self):
        if self.running:
            if random.random() > 0.9: self.latest_emotion = random.choice(["POSITIVE", "NEGATIVE", "Neutral"])
            self.latest_conf = round(random.uniform(0.60, 0.99), 2)

class MockFaceSensor:
    def __init__(self):
        self.latest_emotion = "Waiting..."
        self.latest_conf = 0.0
        self.running = False
    def start(self): self.running = True
    def stop(self): self.running = False
    def process_frame(self):
        if self.running:
            if random.random() > 0.9: self.latest_emotion = random.choice(["Happy", "Sad", "Angry", "Neutral"])
            self.latest_conf = round(random.uniform(0.70, 0.95), 2)

eeg_sensor = MockEEGSensor()
face_sensor = MockFaceSensor()

# --- BACKGROUND WORKER ---
stop_event = threading.Event() # USED TO SIGNAL THREAD TO STOP

def sensor_loop():
    time.sleep(1)
    eeg_sensor.start()
    face_sensor.start()
    
    conn = database.get_db_connection()
    if conn: print("WORKER: Database Connected")
    
    while not stop_event.is_set(): # Stop loop if event is set
        eeg_sensor.process_data()
        face_sensor.process_frame()
        
        # ... (Fusion Logic here) ...
        eeg_data = {"emotion": eeg_sensor.latest_emotion, "conf": eeg_sensor.latest_conf}
        face_data = {"emotion": face_sensor.latest_emotion, "conf": face_sensor.latest_conf}
        
        # Simple Fusion for Test
        final_result = eeg_data['emotion'] if eeg_data['conf'] > 0.8 else face_data['emotion']

        if int(time.time()) % 2 == 0:
            if conn and conn.is_connected():
                try:
                    encrypted_blob = security.encrypt_payload(eeg_data, face_data, final_result)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO sessions (encrypted_data, fusion_result) VALUES (%s, %s)", (encrypted_blob, final_result))
                    conn.commit()
                    cursor.close()
                except Exception:
                    pass
        time.sleep(0.1)

# --- APP LIFECYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    t = threading.Thread(target=sensor_loop, daemon=True)
    t.start()
    yield
    # Shutdown (Run when Ctrl+C is pressed)
    print("SHUTDOWN: Stopping Threads & Releasing Port...")
    stop_event.set() # Tells thread to stop
    eeg_sensor.stop()
    face_sensor.stop()
    time.sleep(0.5) # Give it a moment to close

app = FastAPI(lifespan=lifespan)

if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/live")
async def get_live_data():
    return {
        "eeg": {"emotion": eeg_sensor.latest_emotion, "conf": eeg_sensor.latest_conf},
        "face": {"emotion": face_sensor.latest_emotion, "conf": face_sensor.latest_conf},
        "fusion": "TESTING"
    }

# Secure Admin Routes
@app.get("/logs", response_class=HTMLResponse, dependencies=[Depends(get_current_username)])
async def logs_dashboard(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})

@app.get("/api/history", dependencies=[Depends(get_current_username)])
async def get_history():
    conn = database.get_db_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sessions ORDER BY timestamp DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    
    clean_data = []
    for row in rows:
        clean_data.append({
            "id": row['id'], 
            "time": row['timestamp'], 
            "fusion": row['fusion_result'],
            "details": security.decrypt_payload(row['encrypted_data'])
        })
    return clean_data

# --- ENTRY POINT WITH PORT CLEANUP ---
if __name__ == "__main__":
    print("SECURE TEST MODE STARTING...")
    
    # 1. Register Signal Handler for Clean Exit
    def signal_handler(sig, frame):
        print(" Ctrl+C detected. Exiting...")
        stop_event.set()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)

    # 2. Run Server
    try:
        uvicorn.run(
            "app.main_test:app",
            host="0.0.0.0",
            port=8000,
            ssl_keyfile="certs/key.pem",
            ssl_certfile="certs/cert.pem",
            workers=1 # Single worker prevents zombie processes
        )
    except KeyboardInterrupt:
        pass
    finally:
        print("Port 8000 released.")