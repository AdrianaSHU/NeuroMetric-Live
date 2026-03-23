import os

# PATHS 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "..", "models")

# HARDWARE 
EEG_PORT = "/dev/ttyUSB0" 

# MODELS 
EEG_MODEL_PATH = os.path.join(MODEL_DIR, "seed_sicnet_attention_best.pth")
FACE_MODEL_PATH = os.path.join(MODEL_DIR, "affectnet_hq_attention.tflite")

# ML CONFIGURATION 
EMOTIONS = [
    "anger",    # Index 0
    "contempt", # Index 1
    "disgust",  # Index 2
    "fear",     # Index 3
    "happy",    # Index 4
    "neutral",  # Index 5
    "sad",      # Index 6
    "surprise"  # Index 7
]