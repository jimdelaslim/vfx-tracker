
from models import db, Project
from app import app

with app.app_context():
    connection = db.engine.raw_connection()
    cursor = connection.cursor()
    
    # Check if cache_enabled column exists
    cursor.execute("PRAGMA table_info(projects)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'cache_enabled' not in columns:
        print("Adding cache_enabled column...")
        cursor.execute("ALTER TABLE projects ADD COLUMN cache_enabled BOOLEAN DEFAULT 1")
        connection.commit()
        print("Migration complete!")
    else:
        print("cache_enabled column already exists")
    
    cursor.close()
    connection.close()
