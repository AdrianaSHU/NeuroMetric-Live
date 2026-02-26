import torch
import numpy as np
from scipy import signal
from app.engine.model_def import EEGNet 

class EEGProcessor:
    """
    Edge AI Inference Engine for Electroencephalography (EEG).
    Processes raw brainwave telemetry entirely on the local hardware (Raspberry Pi)
    to ensure zero biometric data leakage to the cloud.
    """
    def __init__(self, model_path):
        # Force computation to the local CPU (Raspberry Pi compatible)
        self.device = torch.device('cpu')
        self.model = EEGNet()
        
        # Load the pre-trained neural network weights securely from local storage
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval() # Lock the model to evaluation mode (disables dropout layers)
        
        # Dynamic Baseline Calibration Tracking
        self.is_calibrated = False
        self.calib_v, self.calib_a = [], []
        self.center_v, self.center_a = 0.5, 0.5 # Default starting points

    def predict(self, raw_data):
        """
        Executes the full EEG pipeline: Slicing -> Downsampling -> Normalization -> Inference.
        Returns a human-readable emotional state based on Valence and Arousal.
        """
        # Ensure we have at least 1 second of data (250 samples at 250Hz)
        if raw_data is None or raw_data.shape[1] < 250:
            return "Calibrating..." if not self.is_calibrated else "Relaxed / Calm"

        # 1. Spatial & Temporal Slicing
        # Isolate the 8 actual EEG channels (index 1 to 8) and grab the most recent 250 samples
        chunk_250 = raw_data[1:9, -250:]
        
        # 2. Downsampling (Feature Reduction)
        # Compress the signal from 250Hz hardware rate to the 128Hz model training rate
        chunk = signal.resample(chunk_250, 128, axis=1)
        
        # 3. Z-Score Normalization
        # Mitigates baseline voltage drift and user skin-impedance variance using: $z = \frac{x - \mu}{\sigma}$
        chunk = (chunk - np.mean(chunk)) / (np.std(chunk) + 1e-6)
        
        # 4. Prepare Tensor for Convolutional Network
        # Reshapes from (Channels, Time) to (Batch, 1, Channels, Time) -> (1, 1, 8, 128)
        tensor = torch.tensor(chunk, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

        # 5. Model Inference (Forward Pass)
        with torch.no_grad(): # Disable gradient tracking to save RAM on the Pi
            logits = self.model(tensor).squeeze()
            
            # Apply Sigmoid activation to squash raw logits into 0.0 - 1.0 probability ranges
            probs = torch.sigmoid(logits).tolist() 
            v, a = probs[0], probs[1] # v = Valence (Positivity), a = Arousal (Energy)

        # 6. Dynamic Calibration Phase
        # Gathers the first 20 valid samples to establish the user's unique resting baseline
        if not self.is_calibrated:
            self.calib_v.append(v)
            self.calib_a.append(a)
            if len(self.calib_v) >= 20:
                self.center_v = np.mean(self.calib_v)
                self.center_a = np.mean(self.calib_a)
                self.is_calibrated = True
            return "Calibrating..."

        # 7. Circumplex Mapping
        # Maps the AI's Valence (v) and Arousal (a) predictions against the user's custom baseline
        if v >= self.center_v and a >= self.center_a: return "Happy / Excited"  # High V, High A
        if v < self.center_v and a >= self.center_a: return "Stressed / Angry"  # Low V, High A
        if v < self.center_v and a < self.center_a: return "Sad / Bored"        # Low V, Low A
        return "Relaxed / Calm"                                                 # High V, Low A