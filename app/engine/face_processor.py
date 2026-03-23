import tensorflow as tf 
import numpy as np
import cv2
from collections import deque
import math

class FaceProcessor:
    def __init__(self, model_path, buffer_size=8): 
        try:
            self.interpreter = tf.lite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self.h = self.input_details[0]['shape'][1]
            self.w = self.input_details[0]['shape'][2]
            self.prediction_buffer = deque(maxlen=buffer_size)
            
            # Calibration State
            self.baseline_noise = np.zeros(8)
            self.is_calibrated = False
            
            print(f"[Face] 15% Elastic Processor Ready: {self.w}x{self.h}")
        except Exception as e:
            print(f"[Face] Model Error: {e}")
            self.interpreter = None

    def calculate_ear(self, landmarks, indices, iw, ih):
        try:
            coords = [(landmarks[i].x * iw, landmarks[i].y * ih) for i in indices]
            v1 = math.dist(coords[1], coords[5])
            v2 = math.dist(coords[2], coords[4])
            h = math.dist(coords[0], coords[3])
            return (v1 + v2) / (2.0 * h)
        except: return 0.0

    def predict(self, face_roi):
        # Fallback array pointing to NEUTRAL (Index 5)
        default_probs = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0])

        if self.interpreter is None or face_roi is None or face_roi.size == 0:
            return default_probs 

        try:
            img = cv2.resize(face_roi, (self.w, self.h))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Keep raw pixels; your .tflite model has a built-in rescaler layer
            input_data = np.expand_dims(img, axis=0).astype(np.float32)

            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            
            # --- CRITICAL FIX: REMOVED DOUBLE-SOFTMAX BUG ---
            # Grab the direct probability distribution from the model
            current_probs = self.interpreter.get_tensor(self.output_details[0]['index'])[0]

            # Personalised Baseline Subtraction
            if self.is_calibrated:
                noise_mask = np.copy(self.baseline_noise)
                noise_mask[5] = 0.0 
                # Gently subtract noise without breaking the probability scale
                current_probs = current_probs - (noise_mask * 0.25) 
                current_probs = np.clip(current_probs, 0.0, 1.0)

            # --- 15% ELASTIC GATE LOGIC ---
            gate_power = 1.2 if not self.is_calibrated else 1.8
            
            happy_score = current_probs[4]
            sad_score = current_probs[6]

            if happy_score < 0.15 and sad_score < 0.15:
                current_probs[5] *= gate_power 
            else:
                current_probs[5] *= 0.3
                if happy_score > sad_score:
                    # Raised from 0.6 to 0.8 so we don't punish real expressions too hard
                    current_probs[4] = math.pow(current_probs[4], 0.8)
                else:
                    current_probs[6] = math.pow(current_probs[6], 0.8)

            # Ensure percentages always equal exactly 100%
            current_probs /= (np.sum(current_probs) + 1e-9)
            
            self.prediction_buffer.append(current_probs)
            return np.mean(self.prediction_buffer, axis=0)
            
        except Exception as e:
            print(f"[Face] Logic Error: {e}")
            return default_probs