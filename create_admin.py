import os
import getpass
import pyotp
import qrcode
from dotenv import load_dotenv
from app.core import database, security

def main():
    load_dotenv()
    print("\n" + "="*45)
    print("   NEURAL FUSION BCI: SECURE ADMIN SETUP   ")
    print("="*45)

    # 1. Collect User Credentials
    username = input("\n[1/3] Enter New Admin Username: ").strip()
    if not username:
        print("!! Error: Username cannot be empty.")
        return

    password = getpass.getpass("[2/3] Enter Admin Password: ")
    confirm = getpass.getpass("      Confirm Password: ")

    if password != confirm:
        print("!! Error: Passwords do not match.")
        return

    # 2. Handle MFA Secret (Check .env first, otherwise generate)
    print("\n[3/3] Configuring Multi-Factor Authentication...")
    mfa_secret = os.getenv("ADMIN_TOTP_SECRET")

    if not mfa_secret:
        print("  > No existing secret found. Generating unique key...")
        mfa_secret = pyotp.random_base32()
        print(f"  > NEW SECRET GENERATED: {mfa_secret}")
    else:
        print("  > Using existing ADMIN_TOTP_SECRET from .env")

    # 3. Generate the QR Code for the phone
    totp = pyotp.TOTP(mfa_secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name="NeuralFusion_BCI")
    
    qr_filename = "mfa_qr_code.png"
    qr_img = qrcode.make(provisioning_uri)
    qr_img.save(qr_filename)

    # 4. Save User to MariaDB
    hashed_pw = security.get_password_hash(password)
    conn = database.get_db_connection()
    if not conn:
        print("!! Error: Could not connect to MariaDB.")
        return

    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO users (username, hashed_password, role, mfa_secret) 
            VALUES (%s, %s, 'superuser', %s)
        """
        cursor.execute(query, (username, hashed_pw, mfa_secret))
        conn.commit()
        
        print("\nSUCCESS" + "-"*43)
        print(f" Admin '{username}' is now in the database.")
        print(f" QR CODE SAVED: {qr_filename}")
        print("-"*45)
        print("\nFINAL INSTRUCTIONS:")
        print(f"1. Open '{qr_filename}' on your Pi and scan with Google Authenticator.")
        print(f"2. IMPORTANT: Run 'rm {qr_filename}' as soon as you finish scanning.")
        print("3. Ensure your .env file contains: ADMIN_TOTP_SECRET=" + mfa_secret)
        print("-"*45 + "\n")

    except Exception as e:
        if "Duplicate entry" in str(e):
            print(f"!! Error: Username '{username}' already exists in database.")
        else:
            print(f"!! Database Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()