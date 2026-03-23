import cv2
import mediapipe as mp
import numpy as np
import threading
import math
import time

class CameraSensor:
    def __init__(self):
        self.cap = None
        self._running = False
        self._lock = threading.Lock()
        self._current_frame = None
        self.last_full_frame = None
        
        self.L_EYE = [362, 385, 387, 263, 373, 380]
        self.R_EYE = [33, 160, 158, 133, 153, 144]
        self.detector = None

    def start(self):
        try:
            self.cap = cv2.VideoCapture(0)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if self.detector is None:
                self.detector = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.6
                )
            
            self._running = True
            threading.Thread(target=self._capture_loop, daemon=True).start()
        except Exception as e:
            print(f"[Hardware] Camera Start Error: {e}")

    def _capture_loop(self):
        while self._running and self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                # The Selfie Mirror
                frame = cv2.flip(frame, 1)
                with self._lock: self._current_frame = frame
            else:
                time.sleep(0.01)

    def get_processed_data(self, emotion_text="NEUTRAL"):
        if self.detector is None or not self._running:
            return None, 0.0

        with self._lock:
            if self._current_frame is None: return None, 0.0
            frame = self._current_frame.copy()

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.detector.process(rgb) 
            
            ear = 0.0
            face_roi = None

            if results.multi_face_landmarks:
                lms = results.multi_face_landmarks[0].landmark
                ih, iw, _ = frame.shape
                
                xs = [lm.x for lm in lms]; ys = [lm.y for lm in lms]
                
                # VISUAL UI BOX: Added a comfortable margin
                ui_pad_w = int(iw * 0.05) # 5% width margin
                ui_pad_h = int(ih * 0.08) # 8% height margin 
                
                x1_ui = max(0, int(min(xs)*iw) - ui_pad_w)
                y1_ui = max(0, int(min(ys)*ih) - ui_pad_h)
                x2_ui = min(iw, int(max(xs)*iw) + ui_pad_w)
                y2_ui = min(ih, int(max(ys)*ih) + ui_pad_h)
                
                color = (198, 218, 3) 
                cv2.rectangle(frame, (x1_ui, y1_ui), (x2_ui, y2_ui), color, 2)
                cv2.rectangle(frame, (x1_ui, y1_ui - 25), (x1_ui + 100, y1_ui), color, -1)
                cv2.putText(frame, emotion_text, (x1_ui + 5, y1_ui - 7), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                # AI CROP BOX: Padded (For the AI's eyes)
                # extracting the large 15%/25% box
                ai_pad_w = int(iw * 0.15) 
                ai_pad_h = int(ih * 0.25) 
                
                x1_ai = max(0, int(min(xs)*iw) - ai_pad_w)
                y1_ai = max(0, int(min(ys)*ih) - ai_pad_h)
                x2_ai = min(iw, int(max(xs)*iw) + ai_pad_w)
                y2_ai = min(ih, int(max(ys)*ih) + ai_pad_h)

                # Feed the LARGER box to the neural network
                face_roi = frame[y1_ai:y2_ai, x1_ai:x2_ai]

                l_ear = self._calc_ear(lms, self.L_EYE, iw, ih)
                r_ear = self._calc_ear(lms, self.R_EYE, iw, ih)
                ear = (l_ear + r_ear) / 2.0

            self.last_full_frame = frame
            return face_roi, ear
        except Exception:
            return None, 0.0

    def stop(self):
        self._running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.detector is not None:
            try:
                self.detector.close()
            except: pass
            self.detector = None

    def _calc_ear(self, landmarks, indices, iw, ih):
        coords = [(landmarks[i].x * iw, landmarks[i].y * ih) for i in indices]
        v1 = math.dist(coords[1], coords[5])
        v2 = math.dist(coords[2], coords[4])
        h = math.dist(coords[0], coords[3])
        return (v1 + v2) / (2.0 * h)