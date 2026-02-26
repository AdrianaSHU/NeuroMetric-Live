import getpass
from app.core import database, security

def reset_password():
    print("--- BCI SYSTEM: ADMIN PASSWORD RESET ---")
    username = input("Enter the Username to reset: ")
    new_password = getpass.getpass("Enter NEW Password: ")
    confirm_password = getpass.getpass("Confirm NEW Password: ")

    if new_password != confirm_password:
        print("ERROR: Passwords do not match.")
        return

    hashed = security.get_password_hash(new_password)
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Update the password for the superuser
        cursor.execute("""
            UPDATE users 
            SET hashed_password = %s 
            WHERE username = %s AND role = 'superuser'
        """, (hashed, username))
        
        if cursor.rowcount == 0:
            print(f"ERROR: User '{username}' not found or is not a superuser.")
        else:
            conn.commit()
            print(f"SUCCESS: Password for '{username}' has been updated.")
            
    except Exception as e:
        print(f"DATABASE ERROR: {e}")
    finally:
        cursor.close(); conn.close()

if __name__ == "__main__":
    reset_password()