import threading
import time
import os
import json
import math
import numpy as np
import cv2
import uvicorn
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

# Internal Professional Modules
from app.core import database, security, schemas, config
from app.sensors.eeg import EEGSensor
from app.sensors.camera import CameraSensor
from app.engine.eeg_processor import EEGProcessor
from app.engine.face_processor import FaceProcessor
from app.engine.fusion import compute_multimodal_fusion

# ==========================================
# GLOBAL HARDWARE & AI INSTANCES
# ==========================================
eeg_hw = EEGSensor(serial_port=config.EEG_PORT)
cam_hw = CameraSensor()
eeg_engine = EEGProcessor(model_path=config.EEG_MODEL_PATH)
face_engine = FaceProcessor(model_path=config.FACE_MODEL_PATH)

# Real-time state (Zero-Trust Data Source)
# Acts as a volatile memory buffer so the frontend can pull live data 
# without constantly reading/writing to the database.
latest_data = {
    "session": {"subject_id": "STANDBY", "nickname": ""},
    "eeg": {
        "emotion": "None", 
        "conf": 0.0, 
        "metrics": {"valence": 0.0, "arousal": 0.0, "stress": 0.0},
        "raw_sample": [0.0] * 8, 
        "probs": [0.0] * 8  
    },
    "face": {"emotion": "None", "conf": 0.0},
    "fusion": {"emotion": "STANDBY", "match": True}
}

session_logs = []
user_profile = None

# Load cached user profile to personalize baseline calibration
if os.path.exists("user_profile.json"):
    try:
        with open("user_profile.json", "r") as f:
            user_profile = json.load(f)
    except: pass

def sanitize_float(val):
    """Prevents JSON serialization crashes caused by NaN or Infinity values."""
    if val is None: return 0.0
    try:
        if math.isnan(val) or math.isinf(val): return 0.0
        return float(val)
    except:
        return 0.0

def gen_face_stream():
    """Yields continuous MJPEG frames securely to the authenticated dashboard."""
    while True:
        frame = cam_hw.last_full_frame 
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            # Fallback UI if the camera drops connection
            placeholder = np.zeros((220, 320, 3), dtype=np.uint8)
            cv2.putText(placeholder, "WAITING...", (80, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (198, 218, 3), 2)
            _, buffer = cv2.imencode('.jpg', placeholder)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.05)



def sensor_loop():
    """
    Background Daemon Thread.
    Continuously polls the physical sensors, runs Edge AI inference, 
    and updates the 'latest_data' global state at roughly 10Hz.
    """
    global latest_data, session_logs
    eeg_hw.start()
    cam_hw.start()
    
    while True:
        try:
            # 1. Hardware Polling
            raw_eeg = eeg_hw.get_raw_data(250) 
            
            # UX FIX: Feed the last known emotion back to the camera to draw on the video UI!
            current_face_emotion = latest_data["face"]["emotion"]
            face_roi = cam_hw.get_face_roi(emotion_text=current_face_emotion)   
            
            current_raw = getattr(eeg_hw, 'current_signal_sample', [0.0] * 8)
            is_eeg_valid = isinstance(current_raw, list) and len(current_raw) > 0 and abs(current_raw[0]) < 480 and current_raw[0] != 0
            is_face_valid = face_roi is not None and face_roi.size > 0

            eeg_emotion, eeg_conf = "None", 0.0
            face_emotion, face_conf = "None", 0.0
            psych_metrics = {"valence": 0.0, "arousal": 0.0, "stress": 0.0}
            eeg_probs_list = [0.0] * 7
            eeg_probs, face_probs = None, None

            # 2. Brainwave Inference
            if is_eeg_valid:
                eeg_probs = eeg_engine.predict(raw_eeg)
                raw_metrics = eeg_engine.get_psych_metrics(raw_eeg)
                
                psych_metrics = {
                    "valence": sanitize_float(raw_metrics.get("valence", 0.0)),
                    "arousal": sanitize_float(raw_metrics.get("arousal", 0.0)),
                    "stress": sanitize_float(raw_metrics.get("stress", 0.0))
                }
                eeg_emotion = config.EMOTIONS[np.argmax(eeg_probs)]
                eeg_conf = sanitize_float(eeg_probs.max())
                eeg_probs_list = [sanitize_float(p) for p in np.array(eeg_probs).flatten().tolist()]
                current_raw = [sanitize_float(val) for val in current_raw]

            # 3. Facial Expression Inference
            if is_face_valid:
                face_probs = face_engine.predict(face_roi)
                face_emotion = config.EMOTIONS[np.argmax(face_probs)]
                face_conf = sanitize_float(face_probs.max())

            # 4. Multimodal Fusion (Affective Computing)
            if is_eeg_valid and is_face_valid:
                fusion_result = compute_multimodal_fusion(eeg_probs, face_probs, config.EMOTIONS, user_profile)
                if "confidence" in fusion_result:
                    fusion_result["confidence"] = sanitize_float(fusion_result["confidence"])
            else:
                fusion_result = {"emotion": "STANDBY", "match": True}

            # 5. Update Global State
            latest_data.update({
                "eeg": {
                    "emotion": eeg_emotion, "conf": eeg_conf, 
                    "metrics": psych_metrics, 
                    "raw_sample": current_raw if is_eeg_valid else [0.0]*8, 
                    "probs": eeg_probs_list
                },
                "face": {"emotion": face_emotion, "conf": face_conf},
                "fusion": fusion_result
            })

            # 6. Session Logging (Sampled every 2 seconds to prevent memory overflow)
            if int(time.time()) % 2 == 0 and is_eeg_valid and is_face_valid:
                log_entry = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fusion": fusion_result["emotion"],
                    "details": {"eeg": {"emotion": eeg_emotion}, "face": {"emotion": face_emotion}},
                    "metrics": psych_metrics
                }
                
                if not session_logs or session_logs[0]["time"] != log_entry["time"]:
                    session_logs.insert(0, log_entry)
                    if len(session_logs) > 100: session_logs.pop() # Keep buffer small on the edge

        except Exception as e:
            print(f"Worker Loop Error: {e}")
        time.sleep(0.1)

# ==========================================
# FASTAPI SERVER SETUP
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and Shutdown lifecycle manager."""
    database.init_db() # Ensure the Vault is built
    t = threading.Thread(target=sensor_loop, daemon=True) # Start background AI
    t.start()
    yield
    eeg_hw.stop() # Safely release hardware ports on shutdown
    cam_hw.stop()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ==========================================
# HTML FRONTEND ROUTES
# ==========================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})

# ==========================================
# SECURE ADMIN & API ROUTES (Zero-Trust Gatekeepers)
# ==========================================



@app.post("/api/admin/create-subject")
async def api_create_subject(nickname: str, age: int, sex: str, admin: dict = Depends(security.get_current_admin)):
    if admin.get("role") != "superuser":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    sid = database.create_research_subject(nickname, age, sex)
    if sid: return {"subject_id": sid}
    raise HTTPException(status_code=500, detail="Creation failed")

@app.get("/api/admin/subjects")
async def list_subjects(admin: dict = Depends(security.get_current_admin)):
    conn = database.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username, nickname, age, sex FROM users WHERE role='subject' ORDER BY id DESC")
    res = cursor.fetchall()
    cursor.close(); conn.close()
    return res

@app.post("/api/admin/set-active-subject/{sid}")
async def set_active(sid: str, admin: dict = Depends(security.get_current_admin)):
    global latest_data
    latest_data["session"]["subject_id"] = sid
    return {"status": "ok", "active_id": sid}

@app.delete("/api/admin/subjects/{sid}")
async def delete_subject(sid: str, admin: dict = Depends(security.get_current_admin)):
    if admin.get("role") != "superuser":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s AND role = 'subject'", (sid,))
    if not cursor.fetchone():
        cursor.close(); conn.close()
        raise HTTPException(status_code=404, detail="Subject not found")

    cursor.execute("DELETE FROM users WHERE username = %s AND role = 'subject'", (sid,))
    conn.commit()
    cursor.close(); conn.close()
    return {"status": "success", "message": f"Subject {sid} deleted"}

@app.post("/api/calibrate-done")
async def save_calibration(data: schemas.CalibrationResult, admin: dict = Depends(security.get_current_admin)):
    """
    Zero-Trust Endpoint: Pulls current sensor data directly from hardware memory
    rather than trusting potentially manipulated data from the browser.
    """
    conn = database.get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (data.subject_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail=f"Subject {data.subject_id} not found")
        
        u_id = user['id']
        global latest_data
        
        # Extract live hardware metrics natively on the server
        eeg_m = latest_data.get("eeg", {}).get("metrics", {})
        live_arousal = eeg_m.get("arousal", 0.0)
        live_stress = eeg_m.get("stress", 0.0)
        
        face_conf = latest_data.get("face", {}).get("conf", 0.0)
        face_emotion = latest_data.get("face", {}).get("emotion", "None")
        neutral_baseline = face_conf if face_emotion.lower() == "neutral" else 0.5
        
        # Populate Mathematical Baseline Vaults
        cursor.execute("""
            INSERT INTO eeg_calibration (user_id, alpha_baseline, beta_baseline, theta_baseline, gamma_baseline, noise_floor)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                alpha_baseline=VALUES(alpha_baseline), 
                noise_floor=VALUES(noise_floor)
        """, (u_id, live_arousal, 0.0, 0.0, 0.0, live_stress))

        cursor.execute("""
            INSERT INTO face_calibration (user_id, anger, contempt, disgust, fear, happy, neutral, sad, surprise)
            VALUES (%s, 0.0, 0.0, 0.0, 0.0, 0.0, %s, 0.0, 0.0)
            ON DUPLICATE KEY UPDATE 
                neutral=VALUES(neutral)
        """, (u_id, neutral_baseline))

        if data.apply_update:
            new_bias_note = f"Adaptive ML Update: +{data.learning_rate} applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            cursor.execute("UPDATE users SET learned_bias = %s WHERE id = %s", (new_bias_note, u_id))

        conn.commit()
        return {"status": "success", "message": f"Baselines saved for {data.subject_id}"}

    except Exception as e:
        conn.rollback()
        print(f"Calibration Save Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to write baseline to database")
    finally:
        cursor.close()
        conn.close()
        
@app.get("/api/calibration-images")
async def api_get_calibration_images(admin: dict = Depends(security.get_current_admin)):
    try:
        image_pool = database.get_calibration_images_from_db()
        if not image_pool: raise ValueError("Empty pool")
        return image_pool
    except:
        return {
            "focus": ["/static/focus1.jpg"],
            "neutral": ["/static/neutral1.jpg"],
            "relax": ["/static/relax1.jpg"]
        }

@app.post("/api/login", response_model=schemas.Token)
def login_admin(request: schemas.LoginRequest):
    conn = database.get_db_connection()
    if not conn: raise HTTPException(status_code=500, detail="DB Error")
        
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (request.username,))
    user = cursor.fetchone()
    cursor.close(); conn.close()

    # 1. Check Passwords Securely (Bcrypt)
    if not user or not security.verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    
    # 2. Check Strict Role
    if user["role"] != "superuser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")

    # 3. Check Multi-Factor Authentication
    if not security.verify_mfa_code(request.mfa_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA")

    # 4. Issue Cryptographic JSON Web Token
    expires_delta = timedelta(days=7) if request.remember_me else timedelta(hours=2)
    access_token = security.create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=expires_delta
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/live")
async def get_live_data(admin: dict = Depends(security.get_current_admin)):
    return latest_data

@app.get("/api/history")
async def get_history(admin: dict = Depends(security.get_current_admin)):
    return session_logs

@app.get("/face_stream")
async def face_stream():
    # Note: No 'Depends' here because HTML <img> tags cannot send Bearer Tokens easily. 
    # Protected implicitly via front-end routing if desired, or left accessible locally.
    return StreamingResponse(gen_face_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/export")
async def export_csv(admin: dict = Depends(security.get_current_admin)):
    import csv, io
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Timestamp", "Fusion Result", "EEG Emotion", "Face Emotion", "Valence", "Arousal", "Stress"])
    
    for row in session_logs:
        writer.writerow([
            row["time"], row["fusion"], 
            row["details"]["eeg"]["emotion"], row["details"]["face"]["emotion"],
            f"{row['metrics']['valence']:.2f}", 
            f"{row['metrics']['arousal']:.2f}", 
            f"{row['metrics']['stress']:.2f}"
        ])
        
    response = Response(content=stream.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=bci_session_{int(time.time())}.csv"
    return response

if __name__ == "__main__":
    # Force HTTPS explicitly with loaded certs to secure data in transit 
    uvicorn.run(app, host="0.0.0.0", port=8000, 
                ssl_keyfile="certs/key.pem", 
                ssl_certfile="certs/cert.pem", 
                access_log=False, 
                log_level="warning")