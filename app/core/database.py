import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv
from passlib.context import CryptContext

# --- Initialization & Configuration ---
load_dotenv()

# Secure password hashing context (using bcrypt for high-entropy protection)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_connection():
    """Establishes a robust connection to the MariaDB 'Vault' using local environment variables."""
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
    """Creates the local storage schema and provisions the initial Admin 'Keymaster'."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    try:
        # --- 1. Users Table ---
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

        # --- 2. Face Calibration Table ---
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

        # --- 3. EEG Calibration Table ---
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

        # --- 4. Calibration Images Table ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calibration_images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phase ENUM('focus', 'neutral', 'relax') NOT NULL,
                image_path VARCHAR(255) NOT NULL UNIQUE
            )
        """)

        # --- 4. Initialize Admin User ---
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


def get_calibration_images_from_db():
    """
    Retrieves local paths for calibration stimuli.
    Organizes them into 'focus', 'neutral', and 'relax' phases.
    """
    conn = get_db_connection()
    if not conn: return None
        
    cursor = conn.cursor(dictionary=True)
    image_pool = {"focus": [], "neutral": [], "relax": []}
    
    try:
        # Checking for the exact table name you have in MariaDB
        cursor.execute("SHOW TABLES LIKE 'eeg_calibration_images'")
        if not cursor.fetchone():
            return None

        # Fetching from the exact table name
        cursor.execute("SELECT phase, image_path FROM eeg_calibration_images")
        rows = cursor.fetchall()
        
        for row in rows:
            phase = row["phase"].lower()
            if phase in image_pool:
                image_pool[phase].append(row["image_path"])
                
        return image_pool
    except Exception as e:
        print(f"Error fetching images: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

# --- Subject Onboarding Logic ---

def generate_next_subject_id(cursor):
    """Calculates S001, S002, etc., ensuring no PII is used in the username."""
    cursor.execute("SELECT username FROM users WHERE username LIKE 'S%' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row and row[0].startswith('S'):
        try:
            last_nr = int(row[0][1:])
            return f"S{(last_nr + 1):03d}"
        except ValueError:
            return "S001"
    return "S001"

def create_research_subject(nickname, age, sex):
    """Provisions a new research subject and initializes their calibration empty-states."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        subject_id = generate_next_subject_id(cursor)
        # Create the primary user record
        cursor.execute("INSERT INTO users (username, nickname, age, sex, role) VALUES (%s, %s, %s, %s, 'subject')", (subject_id, nickname, age, sex))
        new_user_id = cursor.lastrowid
        
        # Initialize the baseline tables for the new subject
        cursor.execute("INSERT INTO face_calibration (user_id) VALUES (%s)", (new_user_id,))
        cursor.execute("INSERT INTO eeg_calibration (user_id) VALUES (%s)", (new_user_id,))
        
        conn.commit()
        return subject_id
    except Error as e:
        print(f"Error creating subject: {e}")
        return None
    finally:
        cursor.close(); conn.close()