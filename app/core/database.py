import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
from passlib.context import CryptContext
from cryptography.fernet import Fernet

# Initialisation & Configuration 
load_dotenv()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialise AES-256 Encryption for the Clinical Vault
VAULT_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher = Fernet(VAULT_KEY.encode())

if not VAULT_KEY:
    raise KeyError(
        "CRITICAL SECURITY ERROR: 'ENCRYPTION_KEY' not found in .env file. "
        "The Clinical Vault cannot be initialized without a valid AES-256 key. [cite: 5, 11]"
    )

try:
    cipher = Fernet(VAULT_KEY.encode())
except Exception as e:
    raise ValueError(f"CRITICAL SECURITY ERROR: Invalid 'ENCRYPTION_KEY' format. {e}")
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),   
            database=os.getenv("DB_NAME", "bci_logs"),
            user=os.getenv("DB_USER"),                
            password=os.getenv("DB_PASSWORD"),
            connect_timeout=5,
            autocommit=True
        )
        return connection
    except Error as e:
        print(f"Database Connection Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    try:
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                nickname VARCHAR(100) NULL,
                age INT NULL,
                sex ENUM('M', 'F', 'Other') NULL,
                hashed_password VARCHAR(255) NULL,
                learned_bias TEXT NULL,
                role ENUM('superuser', 'subject') DEFAULT 'subject',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Face Calibration Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS face_calibration (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                anger FLOAT DEFAULT 0.0,
                contempt FLOAT DEFAULT 0.0,
                disgust FLOAT DEFAULT 0.0,
                fear FLOAT DEFAULT 0.0,
                happy FLOAT DEFAULT 0.0,
                neutral FLOAT DEFAULT 0.0,
                sad FLOAT DEFAULT 0.0,
                surprise FLOAT DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # EEG Calibration Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eeg_calibration (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                alpha_baseline FLOAT DEFAULT 0.0,
                beta_baseline FLOAT DEFAULT 0.0,
                theta_baseline FLOAT DEFAULT 0.0,
                gamma_baseline FLOAT DEFAULT 0.0,
                noise_floor FLOAT DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Initialize Admin User
        admin_user = os.getenv("ADMIN_USER")
        admin_pass = os.getenv("ADMIN_PASS") 
        if admin_user and admin_pass:
            cursor.execute("SELECT id FROM users WHERE username = %s", (admin_user,))
            if not cursor.fetchone():
                hashed_pw = pwd_context.hash(admin_pass)
                cursor.execute("INSERT INTO users (username, hashed_password, role) VALUES (%s, %s, 'superuser')", (admin_user, hashed_pw))
        print("Database initialized successfully.")
    except Error as e:
        print(f"Error during schema creation: {e}")
    finally:
        cursor.close()
        conn.close()

# Local File Scanner 
def get_local_calibration_images():
    """Scans the local static folder for images instead of asking MariaDB."""
    base_dir = "app/static/img/calibration"
    image_pool = {"focus": [], "neutral": [], "relax": []}
    
    try:
        if not os.path.exists(base_dir):
            return image_pool
            
        for filename in os.listdir(base_dir):
            # Only grab images
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue
                
            file_path = f"/static/img/calibration/{filename}"
            name_lower = filename.lower()
            
            if "focus" in name_lower: image_pool["focus"].append(file_path)
            elif "neutral" in name_lower: image_pool["neutral"].append(file_path)
            elif "relax" in name_lower: image_pool["relax"].append(file_path)
            
        return image_pool
    except Exception as e:
        print(f"File scan error: {e}")
        return image_pool

def save_face_calibration(user_id: int, scores: dict):
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO face_calibration (user_id, anger, contempt, disgust, fear, happy, neutral, sad, surprise)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                anger=VALUES(anger), contempt=VALUES(contempt), disgust=VALUES(disgust),
                fear=VALUES(fear), happy=VALUES(happy), neutral=VALUES(neutral),
                sad=VALUES(sad), surprise=VALUES(surprise)
        """
        vals = (
            user_id, scores.get("anger", 0), scores.get("contempt", 0), scores.get("disgust", 0),
            scores.get("fear", 0), scores.get("happy", 0), scores.get("neutral", 0),
            scores.get("sad", 0), scores.get("surprise", 0)
        )
        cursor.execute(query, vals)
        return True
    finally:
        cursor.close(); conn.close()

def save_eeg_calibration(user_id: int, baselines: dict):
    conn = get_db_connection()
    if not conn: return False
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO eeg_calibration (user_id, alpha_baseline, beta_baseline, theta_baseline, gamma_baseline, noise_floor)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                alpha_baseline=VALUES(alpha_baseline), beta_baseline=VALUES(beta_baseline), 
                theta_baseline=VALUES(theta_baseline), gamma_baseline=VALUES(gamma_baseline), 
                noise_floor=VALUES(noise_floor)
        """
        vals = (
            user_id, baselines.get("alpha", 0), baselines.get("beta", 0), 
            baselines.get("theta", 0), baselines.get("gamma", 0), baselines.get("noise", 0)
        )
        cursor.execute(query, vals)
        return True
    finally:
        cursor.close(); conn.close()

def get_subject_baselines(username: str):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT f.neutral as face_neutral, e.alpha_baseline, e.noise_floor
            FROM users u
            LEFT JOIN face_calibration f ON u.id = f.user_id
            LEFT JOIN eeg_calibration e ON u.id = e.user_id
            WHERE u.username = %s
        """
        cursor.execute(query, (username,))
        return cursor.fetchone()
    finally:
        cursor.close(); conn.close()

def generate_next_subject_id(cursor):
    cursor.execute("SELECT username FROM users WHERE username LIKE 'S%' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row and row[0].startswith('S'):
        try:
            last_nr = int(row[0][1:])
            return f"S{(last_nr + 1):03d}"
        except ValueError: return "S001"
    return "S001"

def create_research_subject(nickname, age, sex):
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        subject_id = generate_next_subject_id(cursor)
        cursor.execute("INSERT INTO users (username, nickname, age, sex, role) VALUES (%s, %s, %s, %s, 'subject')", (subject_id, nickname, age, sex))
        new_user_id = cursor.lastrowid
        cursor.execute("INSERT INTO face_calibration (user_id) VALUES (%s)", (new_user_id,))
        cursor.execute("INSERT INTO eeg_calibration (user_id) VALUES (%s)", (new_user_id,))
        conn.commit()
        return subject_id
    finally:
        cursor.close(); conn.close()