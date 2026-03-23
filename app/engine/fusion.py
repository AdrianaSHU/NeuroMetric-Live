import numpy as np

# Neutral is now accepted as a baseline for all states
EMOTION_MAP = {
    "HAPPY": ["HAPPY", "SURPRISE", "NEUTRAL"], 
    "FEAR":  ["FEAR", "ANGER", "SURPRISE"],
    "SAD":   ["SAD", "DISGUST", "CONTEMPT", "NEUTRAL"],
    "NEUTRAL": ["NEUTRAL", "CONTEMPT"]
}

def compute_multimodal_fusion(eeg_input, face_probs, emotions_list, user_profile=None):
    eeg_label = str(eeg_input).strip().upper()
    face_probs = np.array(face_probs).flatten()
    
    if np.sum(face_probs) == 0:
        return {"emotion": "STANDBY", "status": "Offline", "confidence": 0.0}

    face_idx = int(np.argmax(face_probs))
    face_conf = float(face_probs[face_idx])
    face_label = emotions_list[face_idx].upper()

    # WEIGHTED CONFIDENCE (65/35 Split)
    # EEG (Neural Truth) is given more weight than the Optical Mask
    total_confidence = (0.65 * 0.90) + (0.35 * face_conf)

    if "CALIB" in eeg_label:
        return {"emotion": "CALIBRATING", "status": "EEG_BUSY", "confidence": total_confidence}

    allowed_faces = EMOTION_MAP.get(eeg_label, ["NEUTRAL"])
    
    # ACCURACY GATE
    # Dissonance is only triggered if face_conf > 0.65 (High Certainty)
    if face_label in allowed_faces:
        status = "Synced"
        final = eeg_label
    else:
        if face_conf > 0.65:
            status = "Dissonance"
            final = f"MASKED {eeg_label}"
        else:
            # If the camera is unsure, we trust the Brain (EEG)
            status = "Synced"
            final = eeg_label

    return {
        "emotion": final,
        "status": status,
        "confidence": round(total_confidence, 4),
        "details": {"eeg": eeg_label, "face": face_label}
    }