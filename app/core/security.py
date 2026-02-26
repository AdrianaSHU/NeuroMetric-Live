from cryptography.fernet import Fernet
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
import pyotp

# Load environment variables (keeps secrets out of the source code)
load_dotenv()

# ==========================================
# 1. DATA ENCRYPTION (Data at Rest)
# ==========================================

# Define the absolute path for the symmetric encryption key
BASE_DIR = Path(__file__).resolve().parent.parent.parent
KEY_FILE = BASE_DIR / "secret.key"

def load_key():
    """
    Loads the symmetric encryption key from the local filesystem.
    If it doesn't exist, it generates a high-entropy Fernet (AES) key.
    Privacy by Design: Ensures that even if the MariaDB database is stolen, 
    the biometric data is unreadable without this physically separate key file.
    """
    if not KEY_FILE.exists():
        print(f"Generating new Encryption Key at {KEY_FILE}...")
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
    else:
        with open(KEY_FILE, "rb") as key_file:
            key = key_file.read()
    return key

# Initialize the AES cipher suite
cipher_suite = Fernet(load_key())

def encrypt_payload(eeg_data: dict, face_data: dict, fusion_result: str):
    """
    Takes raw biological telemetry, packages it into a JSON blob, 
    and encrypts it before it ever touches the database.
    """
    payload = {
        "eeg": eeg_data,
        "face": face_data,
        "fusion": fusion_result
    }
    json_str = json.dumps(payload)
    encrypted_bytes = cipher_suite.encrypt(json_str.encode('utf-8'))
    return encrypted_bytes.decode('utf-8') 

def decrypt_payload(encrypted_text: str):
    """
    Decrypts the secure database blob back into a Python dictionary 
    for the dashboard or CSV export tools.
    """
    try:
        encrypted_bytes = encrypted_text.encode('utf-8')
        decrypted_bytes = cipher_suite.decrypt(encrypted_bytes)
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        print(f"Decryption Error: {e}")
        return {"error": "Failed to decrypt"}



# ==========================================
# 2. AUTHENTICATION & ACCESS CONTROL
# ==========================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_generate_a_random_long_string")
ALGORITHM = "HS256"

# CryptContext automatically handles salting and iterative hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Tells FastAPI where the frontend should send credentials
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def verify_password(plain_password, hashed_password):
    """Safely compares a plaintext password against the stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Generates a salted bcrypt hash. Raw passwords are never stored."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """
    Generates a stateless JSON Web Token (JWT) for session management.
    Includes an expiration time to enforce session timeouts (default 120 mins).
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=120)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt



def get_current_admin(token: str = Depends(oauth2_scheme)):
    """
    Zero-Trust Gatekeeper Function.
    Every protected API endpoint calls this function first. It verifies the JWT 
    signature and ensures the user has the 'superuser' role before allowing access.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        
        # Enforce strict Role-Based Access Control (RBAC)
        if username is None or role != "superuser":
            raise credentials_exception
            
        token_data = {"username": username, "role": role}
        
    except JWTError:
        raise credentials_exception
        
    return token_data

# ==========================================
# 3. MULTI-FACTOR AUTHENTICATION (MFA)
# ==========================================

def get_totp_secret():
    """Retrieves the Time-Based One-Time Password secret from the environment."""
    secret = os.getenv("ADMIN_TOTP_SECRET")
    if not secret:
        raise ValueError("ADMIN_TOTP_SECRET is not set in the .env file.")
    return secret

def verify_mfa_code(user_submitted_code: str) -> bool:
    """
    Validates the 6-digit code from Google Authenticator/Authy.
    Protects the system against compromised passwords.
    """
    secret = get_totp_secret()
    totp = pyotp.TOTP(secret)
    return totp.verify(user_submitted_code)