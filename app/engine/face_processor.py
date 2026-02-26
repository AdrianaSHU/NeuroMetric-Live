import numpy as np
import cv2
from collections import deque # Lightweight rolling buffer for temporal smoothing

# Edge-Optimized Import: Prefers the lightweight TFLite runtime for Raspberry Pi
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    import tensorflow.lite as tflite

class FaceProcessor:
    """
    Edge AI Inference Engine for Facial Expression Recognition (FER).
    Processes visual telemetry entirely on the local hardware to ensure strict 
    'Privacy by Design' adherence (no raw video feeds are sent to the cloud).
    """
    def __init__(self, model_path, buffer_size=15): 
        # buffer_size=15 equates to roughly ~1 second of video at 15fps.
        # This acts as a low-pass filter to eliminate micro-expression jitter.
        try:
            # Initialize the TFLite Interpreter (Highly optimized for ARM/Raspberry Pi)
            self.interpreter = tflite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            # Dynamically extract expected image dimensions from the model architecture
            self.h = self.input_details[0]['shape'][1]
            self.w = self.input_details[0]['shape'][2]
            
            # --- TEMPORAL SMOOTHING BUFFER ---
            # Automatically drops the oldest frame when the 16th frame is added
            self.prediction_buffer = deque(maxlen=buffer_size)
            
            print(f"Dual-Branch Face Model Loaded: {self.w}x{self.h}")
        except Exception as e:
            print(f"Face Model Error: {e}")
            self.interpreter = None

    def predict(self, face_roi):
        """
        Processes a cropped raw face frame and returns temporally SMOOTHED probabilities.
        """
        if self.interpreter is None or face_roi is None or face_roi.size == 0:
            return np.array([0.0] * 8) 

        try:
            # 1. Standard Preprocessing
            # Resize the cropped face to match the model's input tensor size
            img = cv2.resize(face_roi, (self.w, self.h))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            input_data = np.expand_dims(img, axis=0).astype(np.float32)


            # 2. Edge Inference
            # Push the tensor into the Pi's CPU, calculate, and pull the raw logits out
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            preds = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
            
            # 3. Mathematically Stable Softmax Activation
            # Converts raw model logits into a 0.0 to 1.0 probability distribution.
            # Subtracting the max value prevents mathematical overflow errors on the Pi.
            # Formula: $P(y_i) = \frac{e^{z_i - \max(\mathbf{z})}}{\sum_{j=1}^{K} e^{z_j - \max(\mathbf{z})}}$
            exp_preds = np.exp(preds - np.max(preds))
            current_probs = exp_preds / exp_preds.sum()

            # 4. Temporal Smoothing Logic
            # Append the current frame's probability distribution to the rolling buffer
            self.prediction_buffer.append(current_probs)
            

            # Calculate the mathematical mean across the last N frames to stabilize output
            smoothed_probs = np.mean(self.prediction_buffer, axis=0)
            
            return smoothed_probs
            
        except Exception as e:
            print(f"Face Inference Error: {e}")
            return np.array([0.0] * 8)