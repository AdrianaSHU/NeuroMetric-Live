import cv2
import mediapipe as mp
import numpy as np

class CameraSensor:
    """
    Edge-Optimized Optical Sensor Manager.
    Handles real-time video capture and facial tracking on the Raspberry Pi.
    Enforces 'Privacy by Design' by never saving video feeds to disk; 
    frames are held in volatile RAM just long enough for inference and then destroyed.
    """
    def __init__(self):
        # 0 is the default index for the Pi Camera or primary USB Webcam
        self.cap = cv2.VideoCapture(0)
        
        # Optimization: Force a lower resolution (VGA) to drastically reduce 
        # the CPU load and prevent thermal throttling on the Raspberry Pi.
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Initialize MediaPipe Face Detection
        # We use 'FaceDetection' rather than 'FaceMesh' because it is significantly 
        # lighter on the CPU and perfectly suited for basic bounding box extraction.
        self.mp_face_detection = mp.solutions.face_detection
        self.detector = self.mp_face_detection.FaceDetection(
            model_selection=0, # 0 = Short-range model (best for subjects sitting < 2m from screen)
            min_detection_confidence=0.5
        )
        
        self.last_face_roi = None       
        self.last_full_frame = None     

    def start(self):
        """Wakes up the camera hardware if it was put to sleep."""
        if not self.cap.isOpened():
            self.cap.open(0)

    def get_face_roi(self, emotion_text="ANALYZING..."):
        """
        Grabs the latest frame, locates the face, draws the UI overlays,
        and extracts the cropped Region of Interest (ROI) for the AI model.
        """
        ret, frame = self.cap.read()
        if not ret: 
            return None



        # UX/UI Enhancement: Mirror the frame horizontally.
        # This makes the dashboard video feed act like a mirror, which is much 
        # more comfortable and intuitive for the research subject to look at.
        frame = cv2.flip(frame, 1)
        display_frame = frame.copy()
        ih, iw, _ = frame.shape
        
        # MediaPipe requires RGB format, whereas OpenCV captures in BGR by default
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Memory Optimization: Forcing contiguous memory allocation speeds up 
        # MediaPipe's internal C++ processing significantly.
        rgb_frame = np.ascontiguousarray(rgb_frame)
        rgb_frame.flags.writeable = False 
        
        # Run the lightweight Face Detection
        results = self.detector.process(rgb_frame)

        if results.detections:
            # Grab the highest-confidence face in the frame (index 0)
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            
            # Convert relative coordinates (0.0 - 1.0) to absolute pixel coordinates
            x = int(bbox.xmin * iw)
            y = int(bbox.ymin * ih)
            w = int(bbox.width * iw)
            h = int(bbox.height * ih)
            
            # Padding Logic: The AI model needs to see a bit of the forehead and chin context.
            # max(0, ...) and min(iw/ih, ...) strictly prevent array 'out of bounds' crashes.
            pad = 20
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(iw, x + w + pad), min(ih, y + h + pad)

            # Draw the Tracking Bounding Box (Cyberpunk UI Green)
            box_color = (198, 218, 3) 
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), box_color, 2)
            
            # Draw the live AI Emotion Prediction slightly above the bounding box
            cv2.putText(display_frame, emotion_text, (x1, max(20, y1 - 10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)

            # Extract the final cropped image array to send to the TFLite FaceProcessor
            face_crop = frame[y1:y2, x1:x2]
            
            if face_crop.size > 0:
                self.last_face_roi = face_crop
                self.last_full_frame = display_frame
                return face_crop

        # If no face is detected, we still save the display frame so the UI 
        # doesn't freeze, but we return None for the ROI so the AI pauses.
        self.last_full_frame = display_frame
        self.last_face_roi = None
        return None

    def stop(self):
        """Safely releases the hardware resources."""
        if self.cap.isOpened():
            self.cap.release()
        self.detector.close()