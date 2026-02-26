import os

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "..", "models")

# --- HARDWARE ---
EEG_PORT = "/dev/ttyUSB0" 

# --- MODELS ---
EEG_MODEL_PATH = os.path.join(MODEL_DIR, "EEGNet_Ultracortex_Balanced.pth")
FACE_MODEL_PATH = os.path.join(MODEL_DIR, "affectnet_hq_float32.tflite")

# --- ML CONFIGURATION ---
EMOTIONS = ['anger', 'contempt', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise']