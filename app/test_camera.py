import cv2
import numpy as np
import tensorflow as tf
import time
import os

# Import your project modules
from app.sensors.camera import CameraSensor
from app.engine.face_processor import FaceProcessor
from app.core import config

def run_headless_test():
    print("\n[STEP 1] Initializing Full TensorFlow Interpreter...")
    # Pointing exactly to your model path
    model_path = "models/affectnet_hq_attention.tflite"
    
    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found at {model_path}")
        return

    face_engine = FaceProcessor(model_path=model_path)
    
    print("[STEP 2] Initializing Camera Hardware...")
    cam = CameraSensor()
    cam.start()
    
    print("\n--- SSH LIVE DEBUGGER ACTIVE ---")
    print("AI is now polling the camera. Press Ctrl+C to stop.\n")
    
    try:
        count = 0
        while True:
            # 1. Grab frame from camera
            face_roi = cam.get_face_roi(emotion_text="TESTING...")
            display_frame = cam.last_full_frame
            
            # 2. If face found, run inference
            if face_roi is not None:
                probs = face_engine.predict(face_roi)
                idx = np.argmax(probs)
                emotion = config.EMOTIONS[idx].upper()
                conf = probs[idx] * 100
                
                # Print to terminal
                print(f"FOUND: {emotion} ({conf:.1f}%) | Frames: {count}", end="\r")
                
                # 3. Save a 'Proof of Work' image every 20 frames
                if count % 20 == 0:
                    cv2.imwrite("ssh_debug_snapshot.jpg", display_frame)
            else:
                print("SEARCHING: No face detected in frame...       ", end="\r")
            
            count += 1
            time.sleep(0.05) # Prevent CPU pegging

    except KeyboardInterrupt:
        print("\n\nStopping Test...")
    finally:
        cam.stop()
        print("Camera released. Check 'ssh_debug_snapshot.jpg' for bounding box verification.")

if __name__ == "__main__":
    run_headless_test()