import mysql.connector
import logging
import os
import uuid
import json
from dotenv import load_dotenv
from datetime import datetime
from config import DATABASE_CONFIG # Import config

load_dotenv() # Load environment variables

log = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Database Configuration ---
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': 3306 # Default MySQL port
}

def get_db_connection():
    """Establishes and returns a MySQL database connection."""
    if not all([DATABASE_CONFIG.get('host'), DATABASE_CONFIG.get('user'), DATABASE_CONFIG.get('password'), DATABASE_CONFIG.get('database')]):
         log.error("Database configuration is incomplete.")
         return None
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        if conn.is_connected():
            return conn
        else:
            log.error("Failed to connect to the MySQL database.")
            return None
    except mysql.connector.Error as err:
        log.error(f"MySQL Connection Error: {err}")
        return None
    except Exception as e:
         log.error(f"Unexpected error getting DB connection: {e}")
         return None

def test_connection():
    """Tests the database connection."""
    conn = get_db_connection()
    if conn:
        logging.info("Database connection successful!")
        conn.close()
        return True
    else:
        logging.error("Database connection failed.")
        return False

def initialize_schema():
     """Creates necessary tables if they don't exist (optional)."""
     # It's often better to manage schema migrations separately,
     # but this can be used for initial setup.
     conn = get_db_connection()
     if not conn: return False
     cursor = conn.cursor()
     try:
          # Paste the CREATE TABLE statements from above here
          cursor.execute("""
               CREATE TABLE IF NOT EXISTS search_data (
                   id INT AUTO_INCREMENT PRIMARY KEY,
                   query VARCHAR(512) NOT NULL,
                   date DATE NOT NULL,
                   clicks INT DEFAULT 0,
                   impressions INT DEFAULT 0,
                   ctr DECIMAL(10, 4) DEFAULT 0.0000,
                   position DECIMAL(10, 2) DEFAULT 0.00,
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                   UNIQUE KEY unique_query_date (query(255), date)
               ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
          """)
          cursor.execute("""
               CREATE TABLE IF NOT EXISTS background_tasks (
                   task_id VARCHAR(50) PRIMARY KEY,
                   task_type VARCHAR(50) NOT NULL,
                   payload JSON,
                   status VARCHAR(20) NOT NULL DEFAULT 'pending',
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                   attempts INT DEFAULT 0,
                   last_error TEXT NULL
               ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
          """)
          # Add index creation if not included in CREATE TABLE
          cursor.execute("CREATE INDEX IF NOT EXISTS idx_query ON search_data (query(255));")
          cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON search_data (date);")
          cursor.execute("CREATE INDEX IF NOT EXISTS idx_impressions ON search_data (impressions);")
          cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON background_tasks (status);")

          conn.commit()
          logging.info("Database schema checked/initialized.")
          return True
     except mysql.connector.Error as err:
          logging.error(f"Schema Initialization Error: {err}")
          conn.rollback()
          return False
     finally:
          cursor.close()
          conn.close()

# --- Background Task Functions ---

def add_task(task_type, payload):
    """Adds a new task to the background_tasks table."""
    conn = None
    cursor = None
    task_id = str(uuid.uuid4()) # Generate unique ID
    try:
        conn = get_db_connection()
        if not conn: return None
        cursor = conn.cursor()
        sql = """
            INSERT INTO background_tasks (task_id, task_type, payload, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'pending', %s, %s)
        """
        now = datetime.now()
        # Serialize payload to JSON string
        payload_json = json.dumps(payload)
        cursor.execute(sql, (task_id, task_type, payload_json, now, now))
        conn.commit()
        log.info(f"Added task {task_id} ({task_type}) to queue.")
        return task_id
    except mysql.connector.Error as err:
        log.error(f"DB Error adding task: {err}")
        if conn: conn.rollback()
        return None
    except Exception as e:
        log.error(f"Error adding task: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_pending_tasks(limit=1):
    """Retrieves a specified number of pending tasks."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True) # Fetch as dicts
        # Select tasks that are pending or failed but have attempts left
        sql = """
            SELECT task_id, task_type, payload, attempts
            FROM background_tasks
            WHERE (status = 'pending' OR (status = 'error' AND attempts < %s))
              AND status != 'skip' -- Add this condition
            ORDER BY created_at ASC
            LIMIT %s
        """
        from config import WORKER_CONFIG # Get max retries
        max_retries = WORKER_CONFIG.get('max_task_retries', 3)
        cursor.execute(sql, (max_retries, limit))
        tasks = cursor.fetchall()
        # Deserialize payload from JSON string
        for task in tasks:
             if task.get('payload'):
                  try:
                       task['payload'] = json.loads(task['payload'])
                  except json.JSONDecodeError:
                       log.warning(f"Could not decode payload for task {task['task_id']}")
                       task['payload'] = {} # Set to empty dict on error
        return tasks
    except mysql.connector.Error as err:
        log.error(f"DB Error fetching pending tasks: {err}")
        return []
    except Exception as e:
        log.error(f"Error fetching pending tasks: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def update_task_status(task_id, status, attempts=None, error_message=None):
    """Updates the status, attempts, and optionally error message of a task."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor()
        sql = """
            UPDATE background_tasks
            SET status = %s,
                updated_at = %s,
                attempts = IFNULL(%s, attempts),
                last_error = %s
            WHERE task_id = %s
        """
        now = datetime.now()
        cursor.execute(sql, (status, now, attempts, error_message, task_id))
        conn.commit()
        log.debug(f"Updated task {task_id} status to {status}.")
        return cursor.rowcount > 0 # Return True if a row was updated
    except mysql.connector.Error as err:
        log.error(f"DB Error updating task {task_id} status to {status}: {err}")
        if conn: conn.rollback()
        return False
    except Exception as e:
        log.error(f"Error updating task {task_id} status: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def mark_task_processing(task_id, attempts):
     """Specifically marks a task as processing and increments attempts."""
     # This helps prevent race conditions if multiple workers run
     return update_task_status(task_id, 'processing', attempts=attempts+1)

# Add other database utility functions if needed

if __name__ == '__main__':
     # Example usage: Test connection and initialize schema
     print("Testing DB connection...")
     if test_connection():
          print("Initializing schema...")
          initialize_schema()