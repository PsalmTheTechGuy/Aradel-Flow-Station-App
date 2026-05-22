import os
import shutil
import time
import threading
from datetime import datetime

def run_backup_service(instance_path):
    """
    Background daemon that runs continuously.
    Backs up the SQLite database every 24 hours.
    Cleans up backups older than 30 days.
    """
    app_root = os.path.dirname(instance_path)
    if app_root.endswith('well_test_system'):
        backup_dir = os.path.join(app_root, 'backups')
    else:
        backup_dir = os.path.join(os.path.dirname(instance_path), 'backups')
        
    os.makedirs(backup_dir, exist_ok=True)
    db_path = os.path.join(instance_path, 'well_test.db')
    
    # Run loop
    while True:
        try:
            if os.path.exists(db_path):
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
                backup_filename = f"auto_backup_{timestamp}.db"
                backup_filepath = os.path.join(backup_dir, backup_filename)
                
                # Securely copy the database file
                shutil.copy2(db_path, backup_filepath)
                print(f"[Backup Service] Automated backup created: {backup_filename}")
                
                # Auto-cleanup logic (retain for 30 days)
                now = time.time()
                retention_seconds = 30 * 86400 # 30 days
                
                for filename in os.listdir(backup_dir):
                    if filename.startswith("auto_backup_") and filename.endswith(".db"):
                        file_path = os.path.join(backup_dir, filename)
                        if os.path.isfile(file_path):
                            if os.stat(file_path).st_mtime < now - retention_seconds:
                                os.remove(file_path)
                                print(f"[Backup Service] Deleted old backup: {filename}")
        except Exception as e:
            print(f"[Backup Service] Error: {e}")
            
        # Sleep for 24 hours (86400 seconds) before running again
        time.sleep(86400)

def init_backup_service(app):
    """
    Initializes and starts the background backup thread.
    """
    # Force instance path resolution if not explicitly set
    instance_path = app.instance_path
    if not os.path.exists(instance_path):
        instance_path = os.path.join(app.root_path, 'instance')
        
    # Start thread as daemon so it dies when the Flask app dies
    backup_thread = threading.Thread(target=run_backup_service, args=(instance_path,), daemon=True)
    backup_thread.start()
    print("[Backup Service] Started successfully.")
