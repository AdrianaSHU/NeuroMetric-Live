import numpy as np

EMOTION_MAP = {
    "HAPPY": ["HAPPY", "SURPRISE", "NEUTRAL"], 
    "FEAR":  ["FEAR", "ANGER", "SURPRISE"],
    "SAD":   ["SAD", "DISGUST", "CONTEMPT", "NEUTRAL"],
    "NEUTRAL": ["NEUTRAL", "CONTEMPT"]
}

def compute_multimodal_fusion(eeg_label, eeg_conf, face_probs, emotions_list, user_profile=None):
    # eeg_conf: The Softmax probability from the SICNet-Attention model.
    # face_probs: The raw probability array from the Face model.
    eeg_label = str(eeg_label).strip().upper()
    face_probs = np.array(face_probs).flatten()
    
    # Check for camera/sensor timeout
    if np.sum(face_probs) == 0:
        return {"emotion": "STANDBY", "status": "Offline", "confidence": 0.0}

    # Extract Facial Prediction
    face_idx = int(np.argmax(face_probs))
    face_conf = float(face_probs[face_idx])
    face_label = emotions_list[face_idx].upper()

    # DYNAMIC WEIGHTED CONFIDENCE (65/35 Split)
    # We prioritize the "Neural Truth" but weight it by the model's actual certainty.
    total_confidence = (0.65 * eeg_conf) + (0.35 * face_conf)

    if "CALIB" in eeg_label:
        return {"emotion": "CALIBRATING", "status": "EEG_BUSY", "confidence": total_confidence}

    # Generate allowed list for synchronization check
    allowed_faces = EMOTION_MAP.get(eeg_label, ["NEUTRAL"])
    
    # Apply Personal Baseline: If the user has a "resting neutral bias" in MariaDB,
    # this allow Neutral even if the EEG sees a mild emotion.
    if user_profile and user_profile.get("face_neutral"):
        if face_label == "NEUTRAL" and face_conf < user_profile["face_neutral"]:
            if "NEUTRAL" not in allowed_faces:
                allowed_faces.append("NEUTRAL")

    # ACCURACY GATE LOGIC
    if face_label in allowed_faces:
        status = "Synced"
        final_emotion = eeg_label
    else:
        # Dissonance is only triggered if the Camera is VERY sure (High Certainty)
        if face_conf > 0.65:
            status = "Dissonance Detected"
            final_emotion = f"MASKED {eeg_label}"
        else:
            # If the camera is unsure (low quality), we trust the Brain (EEG)
            status = "Synced"
            final_emotion = eeg_label

    return {
        "emotion": final_emotion,
        "status": status,
        "confidence": round(total_confidence, 4),
        "details": {"eeg": eeg_label, "face": face_label}
    }