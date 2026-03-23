import torch
import numpy as np
from scipy.signal import welch, butter, lfilter, iirnotch
from collections import deque, Counter
from app.engine.model_def import SEED_SICNet8_Attention 

class EEGProcessor:
    def __init__(self, model_path, require_calibration=True):
        self.device = torch.device('cpu') 
        self.model = SEED_SICNet8_Attention()
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval() 
        
        self.emotion_classes = ["NEUTRAL", "SAD", "FEAR", "HAPPY"]
        self.require_calibration = require_calibration
        self.is_calibrated = not require_calibration 
        
        # Buffers for stability
        self.baseline_buffer = []
        self.feature_smoothing_buffer = deque(maxlen=5) 
        self.prediction_window = deque(maxlen=12) # Majority voting window
        
        # Calibration baselines
        self.mean_de = np.full((8, 5), 10.0)  
        self.std_de = np.full((8, 5), 2.0)    
        self.last_probs = [0.25, 0.25, 0.25, 0.25]

    def _apply_hardware_filters(self, data, fs=250):
        """Removes DC drift and 60Hz electrical hum."""
        # Bandpass Filter (1-45 Hz)
        nyq = 0.5 * fs
        low = 1.0 / nyq
        high = 45.0 / nyq
        b, a = butter(5, [low, high], btype='band')
        data = lfilter(b, a, data, axis=1)

        # Notch Filter 
        notch_freq = 50.0 
        quality_factor = 30.0
        b_notch, a_notch = iirnotch(notch_freq, quality_factor, fs)
        data = lfilter(b_notch, a_notch, data, axis=1)
        
        return data

    def compute_de(self, data, fs=250):
        bands = [(1, 4), (4, 8), (8, 13), (13, 30), (30, 45)]
        de_features = np.zeros((8, 5))
        for ch in range(8):
            n_samples = len(data[ch])
            # Ensure nperseg is not larger than data length
            nperseg = min(n_samples, fs)
            freqs, psd = welch(data[ch], fs=fs, nperseg=nperseg)
            for b_idx, (low, high) in enumerate(bands):
                idx_band = np.logical_and(freqs >= low, freqs <= high)
                band_power = np.sum(psd[idx_band]) if np.any(idx_band) else 1e-10
                de_features[ch, b_idx] = 0.5 * np.log(2 * np.pi * np.exp(1) * (band_power + 1e-10))
        return de_features

    def predict(self, raw_data):
        if raw_data is None or raw_data.shape[1] < 100:
            return "AWAITING DATA", [0.25, 0.25, 0.25, 0.25]

        # Extract 8 Cyton channels and clean them
        chunk = raw_data[1:9, :]
        
        # Apply Hardware Filters (Bandpass + Notch)
        filtered_chunk = self._apply_hardware_filters(chunk)
        
        # Calculate Features
        current_de = self.compute_de(filtered_chunk, fs=250)
        self.feature_smoothing_buffer.append(current_de)
        smoothed_de = np.mean(self.feature_smoothing_buffer, axis=0)
        
        # Calibration Phase
        if self.require_calibration and not self.is_calibrated:
            self.baseline_buffer.append(smoothed_de)
            if len(self.baseline_buffer) >= 15: 
                self.mean_de = np.mean(self.baseline_buffer, axis=0)
                self.std_de = np.std(self.baseline_buffer, axis=0) + 1e-5
                self.is_calibrated = True
            return "CALIBRATING...", [0.25, 0.25, 0.25, 0.25]

        # Normalise and Infer
        de_norm = (smoothed_de - self.mean_de) / self.std_de
        tensor = torch.tensor(de_norm, dtype=torch.float32).unsqueeze(0)
        
        with torch.no_grad():
            logits = self.model(tensor).squeeze()
            probs = torch.softmax(logits, dim=0).numpy()
            
        self.last_probs = probs.tolist()
        
        # Majority Voting for Stability
        raw_emotion = self.emotion_classes[np.argmax(probs)]
        self.prediction_window.append(raw_emotion)
        stable_emotion = Counter(self.prediction_window).most_common(1)[0][0]
        
        return stable_emotion, self.last_probs

    def get_psych_metrics(self):
        n, s, f, h = self.last_probs
        return {
            "valence": round(float(h - (s + f)), 2),
            "arousal": round(float(h + f + s), 1),
            "stress": round(float(f), 2)
        }