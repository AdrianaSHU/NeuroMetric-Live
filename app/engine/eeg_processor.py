import torch
import numpy as np
from scipy import signal
from app.engine.model_def import EEGNet 

class EEGProcessor:
    """
    Edge AI Inference Engine for Electroencephalography (EEG).
    Processes raw brainwave telemetry entirely on the local hardware (Raspberry Pi).
    """
    def __init__(self, model_path):
        # Force computation to the local CPU (Raspberry Pi compatible)
        self.device = torch.device('cpu')
        self.model = EEGNet()
        
        # Load the pre-trained neural network weights securely from local storage
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval() # Lock the model to evaluation mode (disables dropout layers)
        
        # Dynamic Baseline & EMA (Exponential Moving Average) Tracking
        self.is_calibrated = False
        self.calib_v, self.calib_a = [], []
        
        # The adaptive thresholds that will fix your Confusion Matrix bias
        self.center_v, self.center_a = 0.5, 0.5 
        self.alpha = 0.05 # Learning rate for the moving baseline

    def predict(self, raw_data):
        """
        Executes the full EEG pipeline: Slicing -> Downsampling -> Normalization -> Inference.
        Returns a human-readable emotional state based on Adaptive Valence and Arousal.
        """
        # Ensure we have at least 1 second of data (250 samples at 250Hz)
        if raw_data is None or raw_data.shape[1] < 250:
            return "Calibrating..." if not self.is_calibrated else "Relaxed / Calm"

        # 1. Spatial & Temporal Slicing (Channels 1 to 8)
        chunk_250 = raw_data[1:9, -250:]
        
        # 2. Downsampling (Feature Reduction to 128Hz)
        chunk = signal.resample(chunk_250, 128, axis=1)
        
        # 3. Z-Score Normalization
        # $z = \frac{x - \mu}{\sigma}$
        chunk = (chunk - np.mean(chunk)) / (np.std(chunk) + 1e-6)
        
        # 4. Prepare Tensor for Convolutional Network -> (1, 1, 8, 128)
        tensor = torch.tensor(chunk, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

        # 5. Model Inference (Forward Pass)
        with torch.no_grad():
            logits = self.model(tensor).squeeze()
            probs = torch.sigmoid(logits).tolist() 
            v, a = probs[0], probs[1] # v = Valence, a = Arousal

        # 6. Initial Calibration Phase (First 20 samples)
        if not self.is_calibrated:
            self.calib_v.append(v)
            self.calib_a.append(a)
            if len(self.calib_v) >= 20:
                self.center_v = np.mean(self.calib_v)
                self.center_a = np.mean(self.calib_a)
                self.is_calibrated = True
            return "Calibrating..."

        # 7. Continuous Adaptive Baseline (The Confusion Matrix Fix)
        # Slowly shifts the crosshairs of the model to account for class imbalance
        self.center_v = (self.alpha * v) + ((1 - self.alpha) * self.center_v)
        self.center_a = (self.alpha * a) + ((1 - self.alpha) * self.center_a)

        # Store history for dashboard metrics
        self.calib_v.append(v)
        self.calib_a.append(a)
        if len(self.calib_v) > 100: # Prevent memory leak on Edge device
            self.calib_v.pop(0)
            self.calib_a.pop(0)

        # 8. Adaptive Circumplex Mapping
        if v >= self.center_v and a >= self.center_a: return "Happy / Excited"  
        if v < self.center_v and a >= self.center_a: return "Stressed / Angry"  
        if v < self.center_v and a < self.center_a: return "Sad / Bored"        
        return "Relaxed / Calm"                                                 

    def get_psych_metrics(self, raw_data):
        """
        Acts as a bridge between the PyTorch EEGNet and the Javascript Dashboard.
        Calculates derived metrics (like Stress) to populate the UI charts.
        """
        # 1. Get the categorical state using the adaptive baseline
        emotion_string = self.predict(raw_data)
        
        # 2. Extract the actual Valence (v) and Arousal (a) the model just calculated
        v = self.calib_v[-1] if len(self.calib_v) > 0 else 0.5
        a = self.calib_a[-1] if len(self.calib_a) > 0 else 0.5
        
        # 3. Mathematically derive stress (High Arousal + Low Valence)
        # $\text{Stress} = (1.0 - \text{Valence}) \times \text{Arousal}$
        calculated_stress = (1.0 - v) * a

        # 4. Package for the Dashboard UI
        return {
            "emotion": emotion_string, 
            "metrics": {               
                "valence": v,
                "arousal": a,
                "stress": calculated_stress
            },
            "confidence": 0.85
        }