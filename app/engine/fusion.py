import numpy as np

# --- SENSOR WEIGHTS & RELIABILITY METRICS ---
# Privacy by Design: These weights allow the system to dynamically distrust 
# the camera (which can be spoofed) in favor of the EEG (which cannot).
CAMERA_RELIABILITY = {
    "anger": 0.39, "contempt": 0.25, "disgust": 0.14, "fear": 0.41,
    "happy": 0.71, "neutral": 0.75, "sad": 0.33, "surprise": 0.42
}

# Circumplex Mapping: Translates specific facial classifications into 
# broader psychological quadrants to match the EEG output.
FACE_TO_QUADRANT = {
    "happy": "Happy / Excited", "surprise": "Happy / Excited",
    "anger": "Stressed / Angry", "fear": "Stressed / Angry", "contempt": "Stressed / Angry",
    "sad": "Sad / Bored", "disgust": "Sad / Bored",
    "neutral": "Relaxed / Calm"
}



def compute_multimodal_fusion(eeg_input, face_probs, emotions_list, user_profile=None):
    """
    Executes a 'Late Fusion' multimodal algorithm.
    Compares neurological intent (EEG) with physiological expression (Face)
    to detect emotional dissonance (e.g., faking a smile).
    """
    # Fallback if camera loses tracking
    if face_probs is None or np.sum(face_probs) == 0:
        # If eeg_input is an array, we default to Standby, otherwise use the string
        quadrant = "STANDBY" if isinstance(eeg_input, (list, np.ndarray)) else eeg_input
        return {"emotion": quadrant, "match": False, "confidence": 0.5}

    # Handle EEG input whether it's passed as a string or raw probabilities
    if isinstance(eeg_input, (list, np.ndarray)):
        # If main.py passes raw probs, fallback to a safe quadrant (or use a threshold)
        eeg_quadrant = "Relaxed / Calm" 
    else:
        eeg_quadrant = str(eeg_input)

    # Extract maximum probability facial emotion
    face_idx = np.argmax(face_probs)
    face_emotion = emotions_list[face_idx].lower() 
    face_quad_guess = FACE_TO_QUADRANT.get(face_emotion, "Relaxed / Calm")
    
    # Normalise strings for comparison
    eeg_clean = eeg_quadrant.lower().replace(" ", "")
    face_clean = face_quad_guess.lower().replace(" ", "")
    match = (eeg_clean == face_clean)
    
    reliability = CAMERA_RELIABILITY.get(face_emotion, 0.5)
    
    # ==========================================
    # 1. DISSONANCE DETECTION (The "Fake" Check)
    # ==========================================
    # If the camera sees high-positivity but the brainwave shows low-valence
    is_faking_happy = (face_emotion == "happy" and "sad" in eeg_quadrant.lower())
    


    # ==========================================
    # 2. FUSION LOGIC & OUTPUT
    # ==========================================
    if is_faking_happy:
        final_emotion = "Social Smile / Bored"
        confidence = 0.45  # Lower confidence because the sensory streams disagree
        status = "Dissonance Detected"
    elif match:
        final_emotion = eeg_quadrant
        confidence = 0.95  # High confidence due to cross-modal synchronization
        status = "Synced"
    else:
        # Conflict Resolution: Default to the highest reliability source
        # If the camera is highly confident (> 60%), trust it. Otherwise, trust the brain.
        final_emotion = face_quad_guess if reliability > 0.6 else eeg_quadrant
        confidence = reliability
        status = "Mixed Signals"

    return {
        "emotion": final_emotion,
        "status": status,
        "confidence": confidence,
        "is_fake": is_faking_happy
    }