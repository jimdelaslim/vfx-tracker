"""Migration script to add internal_notes column to existing databases"""
import sqlite3
import os
import glob

def migrate_database(db_path):
    """Add internal_notes column if it doesn't exist"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(vfx_codes)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'internal_notes' not in columns:
            cursor.execute("ALTER TABLE vfx_codes ADD COLUMN internal_notes TEXT DEFAULT ''")
            conn.commit()
            print(f"✓ Added internal_notes to {db_path}")
        else:
            print(f"  internal_notes already exists in {db_path}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating {db_path}: {e}")
        return False

# Migrate all databases in instance folder
instance_path = 'instance'
if os.path.exists(instance_path):
    db_files = glob.glob(os.path.join(instance_path, '*.db'))
    if db_files:
        print(f"Found {len(db_files)} database(s) to migrate:")
        for db_file in db_files:
            migrate_database(db_file)
    else:
        print("No database files found in instance folder")
else:
    print("No instance folder found - will create column on first run")
