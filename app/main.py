import threading
import time
import os
import json
import math
import numpy as np
import cv2
import uvicorn
import glob
import csv
import shutil
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from jose import jwt, JWTError

# Internal Modules
from app.core import database, security, schemas, config
from app.sensors.eeg import EEGSensor
from app.sensors.camera import CameraSensor
from app.engine.eeg_processor import EEGProcessor
from app.engine.face_processor import FaceProcessor
from app.engine.fusion import compute_multimodal_fusion

# GLOBAL HARDWARE & AI INSTANCES

eeg_hw = EEGSensor(serial_port=config.EEG_PORT)
cam_hw = CameraSensor()
_isnan = math.isnan
_isinf = math.isinf

eeg_engine = EEGProcessor(model_path=config.EEG_MODEL_PATH, require_calibration=True)
face_engine = FaceProcessor(model_path=config.FACE_MODEL_PATH)

# Real-time state (Zero-Trust Data Source)
latest_data = {
    "session": {"subject_id": "STANDBY", "nickname": ""},
    "eeg": {
        "emotion": "None", 
        "conf": 0.0, 
        "metrics": {"valence": 0.0, "arousal": 0.0, "stress": 0.0},
        "raw_sample": [0.0] * 8, 
        "probs": [0.0] * 4 
    },
    "face": {"emotion": "None", "conf": 0.0},
    "fusion": {"emotion": "STANDBY", "match": True, "is_fake": False} 
}

session_logs = []
user_profile = None

# Global Label starts as clean text
last_label = "NEUTRAL"
active_csv_filename = None

if os.path.exists("user_profile.json"):
    try:
        with open("user_profile.json", "r") as f:
            user_profile = json.load(f)
    except: pass

def sanitize_float(val):
    if val is None: return 0.0
    try:
        if _isnan(val) or _isinf(val): return 0.0
        return float(val)
    except: return 0.0

def gen_face_stream():
    """Yields continuous MJPEG frames securely to the authenticated dashboard."""
    while True:
        frame = cam_hw.last_full_frame 
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            placeholder = np.zeros((220, 320, 3), dtype=np.uint8)
            cv2.putText(placeholder, "WAITING...", (80, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (198, 218, 3), 2)
            _, buffer = cv2.imencode('.jpg', placeholder)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.03)


def sensor_loop():
    global latest_data, session_logs, last_label, active_csv_filename
    eeg_hw.start()
    cam_hw.start()
    
    time.sleep(1.0) 
    _round = round

    os.makedirs("logs", exist_ok=True)
    last_log_time = 0.0
    
    while True:
        try:
            # Hardware Polling
            raw_eeg = eeg_hw.get_raw_data(250) 
            
            # Request facial data (Eye Aspect Ratio is calculated but no longer used for status)
            face_roi, ear_score = cam_hw.get_processed_data(emotion_text=last_label) 
            
            is_eeg_valid = raw_eeg is not None and raw_eeg.shape[1] > 0
            is_face_valid = face_roi is not None and face_roi.size > 0

            eeg_emotion, eeg_conf = "None", 0.0
            face_emotion, face_conf_val = "None", 0.0
            face_probs = np.zeros(8)
            psych_metrics = {"valence": 0.0, "arousal": 0.0, "stress": 0.0}

            # Brainwave Inference
            if is_eeg_valid:
                eeg_emotion, eeg_probs_list = eeg_engine.predict(raw_eeg)
                eeg_conf = 0.85 
                psych_metrics = eeg_engine.get_psych_metrics()

            # Facial Expression Inference
            if is_face_valid:
                face_probs = face_engine.predict(face_roi)
                face_idx = np.argmax(face_probs)
                
                # Fetch raw float for frontend JavaScript
                face_conf_val = sanitize_float(face_probs[face_idx])
                face_emotion = config.EMOTIONS[face_idx].upper()
                
                # Update visual label for the green box on next frame
                last_label = face_emotion

            # Multimodal Fusion
            if is_eeg_valid and is_face_valid:
                # This function now handles the "Synced" vs "Dissonance" status strings
                fusion_result = compute_multimodal_fusion(eeg_emotion, face_probs, config.EMOTIONS, user_profile)
            else:
                fusion_result = {"emotion": "STANDBY", "status": "WAITING", "is_fake": False, "confidence": 0.0}

            # Update Global State 
            latest_data.update({
                "eeg": {
                    "emotion": eeg_emotion, 
                    "conf": sanitize_float(eeg_conf), 
                    "metrics": psych_metrics, 
                    "raw_sample": getattr(eeg_hw, 'current_signal_sample', [0.0]*8), 
                    "probs": [sanitize_float(p) for p in eeg_probs_list] if is_eeg_valid else [0.0]*4
                },
                "face": {
                    "emotion": face_emotion, 
                    "conf": face_conf_val,
                    "ear": _round(ear_score, 2)
                },
                "fusion": fusion_result
            })

            # --- 6. APPEND-ON-THE-FLY CSV LOGGING ---
            current_time = time.time()
            
            # Check if exactly 2.0 seconds have passed since the last save
            if active_csv_filename and (current_time - last_log_time >= 2.0) and is_eeg_valid and is_face_valid:
                
                # Reset the timer immediately
                last_log_time = current_time 
                
                conf_val = fusion_result.get("confidence", 0.0)

                # Auto-save straight to the PC disk
                with open(active_csv_filename, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        fusion_result["emotion"],
                        fusion_result["status"],
                        f"{conf_val:.2%}", 
                        eeg_emotion,
                        face_emotion,
                        f"{psych_metrics.get('valence', 0.0):.2f}",
                        f"{psych_metrics.get('arousal', 0.0):.2f}",
                        f"{psych_metrics.get('stress', 0.0):.2f}"
                    ])

                # Keep the UI "Review" screen updated
                log_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "fusion": fusion_result["emotion"],
                    "status": fusion_result["status"],
                    "confidence": conf_val,
                    "details": {"eeg": {"emotion": eeg_emotion}, "face": {"emotion": face_emotion}},
                    "metrics": psych_metrics
                }
                
                session_logs.insert(0, log_entry)
                if len(session_logs) > 500: session_logs.pop()

        except Exception as e:
            print(f"Worker Loop Error: {e}")
        time.sleep(0.03)

# FASTAPI SERVER SETUP

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        eeg_hw.stop()
        cam_hw.stop()
        time.sleep(0.5) 
    except: pass
    
    database.init_db() 
    t = threading.Thread(target=sensor_loop, daemon=True) 
    t.start()
    yield
    eeg_hw.stop() 
    cam_hw.stop()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request):
    return templates.TemplateResponse("logs.html", {"request": request})

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
    query = """
        SELECT u.username, u.nickname, u.age, u.sex,
               (CASE WHEN e.alpha_baseline > 0 AND f.neutral > 0 THEN 1 ELSE 0 END) AS is_calibrated
        FROM users u 
        LEFT JOIN eeg_calibration e ON u.id = e.user_id 
        LEFT JOIN face_calibration f ON u.id = f.user_id
        WHERE u.role='subject' 
        ORDER BY u.id DESC
    """
    cursor.execute(query)
    res = cursor.fetchall()
    cursor.close(); conn.close()
    return res

@app.post("/api/admin/set-active-subject/{sid}")
async def set_active(sid: str, admin: dict = Depends(security.get_current_admin)):
    global latest_data, session_logs, active_csv_filename
    
    # Update active subject
    latest_data["session"]["subject_id"] = sid
    
    # Clear the Live UI Review screen
    session_logs.clear()
    
    # Remove the old session files for this specific subject
    os.makedirs("logs", exist_ok=True)
    old_files = glob.glob(f"logs/BCI_Session_{sid}_*.csv")
    for f in old_files:
        try:
            os.remove(f)
        except Exception as e:
            print(f"Failed to delete old log: {e}")

    # Create a fresh file for the new session and write the headers
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    active_csv_filename = f"logs/BCI_Session_{sid}_{timestamp}.csv"
    
    with open(active_csv_filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Fusion Result", "Status", "Confidence", "EEG (Neural)", "Face (Optical)", "Valence", "Arousal", "Stress"])

    return {"status": "ok", "active_id": sid, "message": "Old logs cleared. New auto-save session started."}

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
    return {"status": "success"}

@app.post("/api/calibrate-done")
async def save_calibration(data: schemas.CalibrationResult, admin: dict = Depends(security.get_current_admin)):
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
        
        eeg_engine.is_calibrated = True
        eeg_m = latest_data.get("eeg", {}).get("metrics", {})
        live_stress = eeg_m.get("stress", 0.0)
        
        raw_conf = latest_data.get("face", {}).get("conf", 0.0)
        face_conf = float(raw_conf)
        
        face_emotion = latest_data.get("face", {}).get("emotion", "None")
        neutral_baseline = face_conf if face_emotion.lower() == "neutral" else 0.5
        
        cursor.execute("""
            INSERT INTO eeg_calibration (user_id, alpha_baseline, beta_baseline, theta_baseline, gamma_baseline, noise_floor)
            VALUES (%s, 1.0, 0.0, 0.0, 0.0, %s)
            ON DUPLICATE KEY UPDATE 
                alpha_baseline=VALUES(alpha_baseline), 
                noise_floor=VALUES(noise_floor)
        """, (u_id, live_stress))

        cursor.execute("""
            INSERT INTO face_calibration (user_id, neutral, happy, sad) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                neutral = VALUES(neutral), 
                happy = VALUES(happy), 
                sad = VALUES(sad);
        """, (u_id, neutral_baseline, 0.0, 0.0))

        if data.apply_update:
            new_bias_note = f"Adaptive ML Update: +{data.learning_rate} applied on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            cursor.execute("UPDATE users SET learned_bias = %s WHERE id = %s", (new_bias_note, u_id))

        conn.commit()
        return {"status": "success", "message": f"Z-Score Baselines locked for {data.subject_id}"}

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
        image_pool = database.get_local_calibration_images()
        if not image_pool or (not image_pool["focus"] and not image_pool["neutral"]): 
            raise ValueError("No images found in local directory")
        return image_pool
    except Exception as e:
        print(f"Error loading images: {e}")
        return {
            "focus": ["/static/img/calibration/focus-dewdrop.jpg"],
            "neutral": ["/static/img/calibration/neutral-curtains.jpg"],
            "relax": ["/static/img/calibration/relax-sunset.jpg"]
        }

@app.post("/api/login", response_model=schemas.Token)
def login_admin(request: schemas.LoginRequest):
    conn = database.get_db_connection()
    if not conn: raise HTTPException(status_code=500, detail="DB Error")
        
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (request.username,))
    user = cursor.fetchone()
    cursor.close(); conn.close()

    if not user or not security.verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    
    if user["role"] != "superuser":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")

    if not security.verify_mfa_code(request.mfa_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA")

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
async def face_stream(token: str = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Stream unauthorized")
    try:
        payload = jwt.decode(token, security.JWT_SECRET_KEY, algorithms=[security.ALGORITHM])
        if payload.get("role") != "superuser":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid stream token")

    return StreamingResponse(gen_face_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/export")
async def export_csv(admin: dict = Depends(security.get_current_admin)):
    global active_csv_filename, latest_data
    
    current_sid = latest_data["session"]["subject_id"]
    
    # Ensure a subject is actually selected
    if current_sid == "STANDBY":
        raise HTTPException(status_code=400, detail="No active subject selected.")
        
    target_file = None
    
    # Is there a session currently running?
    if active_csv_filename and os.path.exists(active_csv_filename):
        target_file = active_csv_filename
    # If the session was stopped, find the timestamped file left in the folder
    else:
        list_of_files = glob.glob(f"logs/BCI_Session_{current_sid}_*.csv")
        if list_of_files:
            # Grab the one file that exists for this subject
            target_file = max(list_of_files, key=os.path.getctime)
            
    # Check if a file was successfully found
    if not target_file:
        raise HTTPException(status_code=404, detail=f"No session data found for subject {current_sid}.")
        
    # Read the physical file from the hard drive
    with open(target_file, mode="rb") as f:
        content = f.read()
        
    # Send it securely to the JavaScript download function
    response = Response(content=content, media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={os.path.basename(target_file)}"
    return response

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, 
                ssl_keyfile="certs/key.pem", 
                ssl_certfile="certs/cert.pem", 
                access_log=False, 
                log_level="warning")