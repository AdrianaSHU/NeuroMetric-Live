from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# --- Authentication Schemas ---

class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: str  # Time-based One-Time Password (TOTP)
    remember_me: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str

# --- User & Research Subject Schemas ---

class UserResponse(BaseModel):
    id: int
    username: str  # Usually a pseudonymized Subject ID (e.g., S001)
    role: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- BCI Stimuli & Calibration Schemas ---

class EEGImageResponse(BaseModel):
    id: int
    phase: str  # Neutral, Focus, or Relax
    image_path: str
    model_config = ConfigDict(from_attributes=True)

class FaceCalibrationSchema(BaseModel):
    anger: float = 0.0
    contempt: float = 0.0
    disgust: float = 0.0
    fear: float = 0.0
    happy: float = 0.0
    neutral: float = 0.0
    sad: float = 0.0
    surprise: float = 0.0
    model_config = ConfigDict(from_attributes=True)

class EEGCalibrationSchema(BaseModel):
    alpha_baseline: float = 0.0
    beta_baseline: float = 0.0
    theta_baseline: float = 0.0
    gamma_baseline: float = 0.0
    noise_floor: float = 0.0
    model_config = ConfigDict(from_attributes=True)

class CalibrationResult(BaseModel):
    subject_id: str
    apply_update: bool
    learning_rate: float