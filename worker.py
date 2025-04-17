# worker.py
import os
import logging
import time
import requests
import json
import random # For jitter
from dotenv import load_dotenv # Import load_dotenv
import sys # For printing to stderr during debug and sys.exit
from datetime import datetime
from database import get_wordpress_db_connection

# --- Load .env Before Other Imports ---
# Construct the path relative to this script file or use absolute path
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
# Or use absolute path: dotenv_path = '/home/eslobrown/seobot/.env'
print(f"WORKER: Attempting to load .env from: {dotenv_path}", file=sys.stderr) # Use print for early debug
if os.path.exists(dotenv_path):
    loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
    print(f"WORKER: load_dotenv returned: {loaded}", file=sys.stderr)
else:
    print(f"WORKER: ERROR - .env file not found at {dotenv_path}", file=sys.stderr)
    loaded = False
# --- End .env Loading ---


# --- !! HARDCODED PRE-CHECK !! ---
# Check variables immediately after loading .env and BEFORE defining functions or importing config
print("--- HARDCODED PRE-CHECK ---", file=sys.stderr)
wp_api_url_check = os.getenv('WP_API_URL')
wp_api_user_check = os.getenv('WP_API_USER')
wp_api_password_check = os.getenv('WP_API_APP_PASSWORD')
db_host_check = os.getenv('DB_HOST')
anthropic_key_check = os.getenv('ANTHROPIC_API_KEY') # Add Anthropic check here

print(f"HARDCODED CHECK: WP_API_URL = {wp_api_url_check}", file=sys.stderr)
print(f"HARDCODED CHECK: WP_API_USER = {wp_api_user_check}", file=sys.stderr)
print(f"HARDCODED CHECK: WP_API_APP_PASSWORD = {'********' if wp_api_password_check else None}", file=sys.stderr)
print(f"HARDCODED CHECK: DB_HOST = {db_host_check}", file=sys.stderr)
print(f"HARDCODED CHECK: ANTHROPIC_API_KEY = {'********' if anthropic_key_check else None}", file=sys.stderr)

# Optional: Stop execution if critical creds are missing right away
if not wp_api_url_check or not wp_api_user_check or not wp_api_password_check:
    print("FATAL: Required WP credentials missing immediately after load_dotenv! Exiting worker.", file=sys.stderr)
    sys.exit("FATAL: Missing required WP credentials in environment for worker.")
if not anthropic_key_check:
    print("FATAL: ANTHROPIC_API_KEY missing immediately after load_dotenv! Exiting worker.", file=sys.stderr)
    sys.exit("FATAL: Missing ANTHROPIC_API_KEY in environment for worker.")

print("--- Passed HARDCODED PRE-CHECK ---", file=sys.stderr)
# --- !! END HARDCODED CHECK !! ---


# --- Now import the rest AFTER .env load and initial check ---
# config module will re-read using os.getenv, but pre-check ensures they are loaded
import config
import database # DB functions for tasks

# Import your service classes
from services.search_console import SearchConsoleAPI, SearchConsoleDataProcessor
from services.content_analyzer import ContentAnalyzer
from services.imagen import ImagenClient
from services.wordpress import WordPressService # Needs updated __init__
from services.workflow import ContentWorkflowService # Needs updated __init__


# Configure logging (logs to file and console)
LOG_FILE = '/home/eslobrown/seobot/worker_always_on.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s', # Added funcName
    handlers=[
        logging.FileHandler(LOG_FILE), # Log to file
        logging.StreamHandler(sys.stdout) # Log to stdout (visible in Always-On Task console/log)
    ]
)
log = logging.getLogger(__name__)


# --- Worker Functions ---

def process_single_task(task):
    """Processes a single generation task."""
    task_id = task.get('task_id', 'UNKNOWN_TASK_ID')
    payload = task.get('payload', {}) # Use .get for safety
    attempts = task.get('attempts', 0)
    log.info(f"Processing task {task_id} (Attempt {attempts+1}) - Type: {task.get('task_type', 'UNKNOWN_TYPE')}")

    # --- Basic Payload Validation ---
    if not payload:
         log.error(f"Task {task_id} has empty or invalid payload. Marking as error.")
         database.update_task_status(task_id, 'error', error_message="Invalid or empty payload received.")
         return

    required_payload_keys = ['brief_id', 'prompt', 'target_word_count', 'keyword', 'callback_url']
    missing_keys = [key for key in required_payload_keys if key not in payload]
    if missing_keys:
        error_msg = f"Task {task_id} payload missing required keys: {', '.join(missing_keys)}"
        log.error(error_msg)
        database.update_task_status(task_id, 'error', error_message=error_msg)
        return
    # --- End Payload Validation ---


    # Mark task as processing in DB
    if not database.mark_task_processing(task_id, attempts):
         log.warning(f"Failed to mark task {task_id} as processing (maybe already processed?). Skipping.")
         return

    # --- Initialize Services ---
    wp_service = None # Initialize to None
    try:
        # --- Get WP variables directly using os.getenv ---
        wp_api_url = os.getenv('WP_API_URL')
        wp_api_user = os.getenv('WP_API_USER')
        wp_api_password = os.getenv('WP_API_APP_PASSWORD')
        log.info(f"DEBUG [Task {task_id}]: PRE-INIT CHECK: WP_API_URL = {wp_api_url}")
        log.info(f"DEBUG [Task {task_id}]: PRE-INIT CHECK: WP_API_USER = {wp_api_user}")
        log.info(f"DEBUG [Task {task_id}]: PRE-INIT CHECK: WP_API_APP_PASSWORD = {'********' if wp_api_password else None}")
        if not wp_api_url or not wp_api_user or not wp_api_password:
             raise ValueError("WP Credentials check failed inside task processing.")
        # Pass individual vars to WordPressService (ensure its __init__ expects these)
        wp_service = WordPressService(
            wp_api_url, 
            wp_api_user, 
            wp_api_password, 
            db_connection_func=database.get_db_connection,  # For PythonAnywhere DB
            wp_db_connection_func=database.get_wordpress_db_connection  # For WordPress DB
)

        # --- Get Anthropic variables directly ---
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        anthropic_model = os.getenv('CLAUDE_MODEL', 'claude-3-haiku-20240307') # Use default from .env if not set
        anthropic_max_tokens = int(os.getenv('CLAUDE_MAX_TOKENS', '8000'))
        anthropic_rate_limit = int(os.getenv('CLAUDE_RATE_LIMIT_PER_MINUTE', '50'))
        anthropic_max_retries = int(os.getenv('CLAUDE_MAX_RETRIES', '3'))
        log.info(f"DEBUG [Task {task_id}]: Read ANTHROPIC_API_KEY = {'********' if anthropic_key else None}")
        if not anthropic_key:
             raise ValueError("ANTHROPIC_API_KEY check failed inside task processing.")
        # ---

        # Initialize other services using config dictionaries
        gemini_key = config.GOOGLE_CONFIG.get('gemini_api_key')
        gemini_model = config.GOOGLE_CONFIG.get('gemini_image_model')
        if not gemini_key: raise ValueError("Missing GEMINI_API_KEY from config")
        imagen_client = ImagenClient(gemini_key, gemini_model)

        # Pass necessary Google config parts to ContentAnalyzer if needed
        content_analyzer = ContentAnalyzer(config.GOOGLE_CONFIG, database.get_db_connection, wp_service)

        # Pass individual Anthropic vars to ContentWorkflowService
        # (Ensure ContentWorkflowService.__init__ expects these specific args)
        workflow_service = ContentWorkflowService(
            anthropic_api_key=anthropic_key,
            anthropic_model=anthropic_model,
            anthropic_max_tokens=anthropic_max_tokens,
            anthropic_rate_limit=anthropic_rate_limit,
            anthropic_max_retries=anthropic_max_retries,
            content_analyzer=content_analyzer,
            imagen_client=imagen_client,
            wordpress_service=wp_service
        )
        # --- End Service Initialization ---

        log.info(f"Services initialized successfully for task {task_id}")

    except ValueError as ve: # Catch specific credential/config errors during init
         error_msg = f"Failed to initialize services for task {task_id}: {ve}"
         log.error(error_msg)
         database.update_task_status(task_id, 'error', error_message=str(ve)) # Store specific error
         return # Stop processing this task
    except Exception as init_err: # Catch other potential init errors
         error_msg = f"Unexpected error initializing services for task {task_id}: {init_err}"
         log.error(error_msg, exc_info=True) # Log full traceback
         database.update_task_status(task_id, 'error', error_message=error_msg)
         return # Stop processing this task


    # --- Execute Task Logic ---
    callback_payload = {
        'brief_id': payload['brief_id'],
        'task_id': task_id,
        'status': 'error', # Default
        'generated_content': None,
        'featured_image_id': None,
        'generated_post_id': None, # Add placeholder
        'generated_post_url': None, # <-- ADD PLACEHOLDER
        'error_message': 'Task execution did not complete successfully.'
    }
    start_time = time.time()
    final_task_status = 'error'

    try:
        if task.get('task_type') == 'generate_content':
            log.info(f"Generating content for keyword: {payload['keyword']} [Task {task_id}]")
            # Prepare brief data for generation service
            mock_brief = {
                'keyword': payload['keyword'],
                'prompt': payload['prompt'],
                'target_word_count': payload['target_word_count'],
                # Include other necessary fields if _generate_claude_prompt needs them
            }
            # Call the generation function within workflow service
            generated_content, gen_error = workflow_service.generate_content(mock_brief)

            if generated_content:
                log.info(f"Content generated successfully for task {task_id}.")
                callback_payload['generated_content'] = generated_content

                # --- Generate Featured Image ---
                log.info(f"Generating featured image for task {task_id}")
                content_snippet = generated_content[:500]
                featured_image_id = workflow_service.generate_and_upload_featured_image(
                    payload['keyword'], content_snippet
                )
                callback_payload['featured_image_id'] = featured_image_id
                if featured_image_id:
                     log.info(f"Featured image generated/uploaded (ID: {featured_image_id}) for task {task_id}")
                else:
                     log.warning(f"Failed to generate/upload featured image for task {task_id}")

                # --- Create WordPress Post with Generated Content ---
                log.info(f"Creating WordPress post for task {task_id}")
                mock_brief = {
                    'keyword': payload['keyword'],
                    'target_word_count': payload['target_word_count']
                    # Add other necessary fields
                }
                post_result = workflow_service.post_content_to_wordpress(
                    mock_brief, generated_content, featured_image_id
                )

            if post_result and post_result.get('blog_post', {}).get('status') == 'success':
                blog_post_info = post_result['blog_post']
                callback_payload['generated_post_id'] = blog_post_info.get('id')
                callback_payload['generated_post_url'] = blog_post_info.get('url') # <-- CAPTURE URL
                log.info(f"Created WordPress post ID: {blog_post_info.get('id')} with URL: {blog_post_info.get('url')}")
                # Mark overall success if post created
                callback_payload['status'] = 'success'
                callback_payload['error_message'] = None
                final_task_status = 'completed'

                # Handle category update status from result if needed
                category_update_info = post_result.get('category_update', {})
                if category_update_info.get('status') == 'error':
                    log.warning(f"Category update part failed: {category_update_info.get('error')}")
                    # Decide if this should downgrade overall status? For now, keep 'completed' if post was made.
                    # callback_payload['status'] = 'partial_error' # Example status
                    callback_payload['error_message'] = f"Blog post created, but category update failed: {category_update_info.get('error')}"


            elif post_result and post_result.get('blog_post', {}).get('status') == 'error':
                 # Blog post creation specifically failed
                 error_detail = post_result['blog_post'].get('error', 'Unknown WP error')
                 callback_payload['error_message'] = f"Content generated, but WP post creation failed: {error_detail}"
                 log.error(f"Failed to create WordPress post for task {task_id}: {error_detail}")
                 final_task_status = 'error'
            else:
                 # Content generation failed earlier
                 callback_payload['error_message'] = f"Content generation failed: {gen_error}" # Use error from generate_content
                 log.error(f"Content generation failed for task {task_id}: {gen_error}")
                 final_task_status = 'error'

        else:
            # Handle unknown task types
            callback_payload['error_message'] = f"Unknown task type received: {task.get('task_type')}"
            log.error(callback_payload['error_message'])
            final_task_status = 'error'

    except Exception as processing_err:
        # Catch unexpected errors during the main processing block
        error_msg = f"Unexpected error processing task {task_id}: {str(processing_err)}"
        log.exception(error_msg) # Log full traceback
        callback_payload['error_message'] = error_msg
        callback_payload['status'] = 'error'
        final_task_status = 'error'

    finally:
        # --- Send Callback to WordPress ---
        callback_url = payload.get('callback_url', config.WP_CONFIG.get('callback_url'))
        if callback_url:
            log.info(f"Sending callback for task {task_id} to {callback_url} with final task status '{final_task_status}' and callback status '{callback_payload['status']}'")
            try:
                headers = {'Content-Type': 'application/json'}
                # Re-check WP credentials directly from environment for callback safety
                wp_user = os.getenv('WP_API_USER')
                wp_pass = os.getenv('WP_API_APP_PASSWORD')
                if not wp_user or not wp_pass:
                     raise ValueError("Missing WP API credentials for callback.")

                auth = (wp_user, wp_pass)

                wp_callback_data = {
                     'brief_id': callback_payload['brief_id'],
                     'task_id': callback_payload['task_id'],
                     'status': callback_payload['status'],
                     # Only send content if successful? Optional. Might be large.
                     # 'generated_content': callback_payload.get('generated_content') if callback_payload.get('status') == 'success' else None,
                     'generated_post_id': callback_payload.get('generated_post_id'),
                     'generated_post_url': callback_payload.get('generated_post_url'), # <-- INCLUDE URL
                     'featured_image_id': callback_payload.get('featured_image_id'),
                     'error_message': callback_payload.get('error_message')
                }
                # Remove keys with None values before sending JSON
                wp_callback_data_clean = {k: v for k, v in wp_callback_data.items() if v is not None}

                response = requests.post(
                    callback_url,
                    json=wp_callback_data_clean, # Send cleaned data
                    headers=headers,
                    auth=auth,
                    timeout=60
                )
                response.raise_for_status()
                log.info(f"Callback successful for task {task_id} (WP Status: {response.status_code})")

            except requests.exceptions.RequestException as req_err:
                error_msg = f"Callback failed for task {task_id}: {req_err}"
                log.error(error_msg)
                final_task_status = 'error' # Mark task as error if callback failed
                callback_payload['error_message'] = f"Processing status was '{callback_payload['status']}', but callback failed: {req_err}"

            except ValueError as val_err: # Catch missing WP creds for callback
                 error_msg = f"Callback failed for task {task_id}: {val_err}"
                 log.error(error_msg)
                 final_task_status = 'error'
                 callback_payload['error_message'] = error_msg

            except Exception as cb_err:
                 error_msg = f"Unexpected error during callback for task {task_id}: {cb_err}"
                 log.exception(error_msg)
                 final_task_status = 'error'
                 callback_payload['error_message'] = f"Callback error: {cb_err}"
        else:
            log.error(f"No callback URL found for task {task_id}. Cannot notify WordPress. Marking task as '{final_task_status}' in DB.")
            # Keep final_task_status as determined by processing, but WP won't know
            callback_payload['error_message'] = "Missing callback URL in task payload"

        # --- Update Final Task Status in DB ---
        database.update_task_status(
             task_id,
             final_task_status, # 'completed' or 'error'
             error_message=callback_payload.get('error_message') # Log last relevant error
        )
        end_time = time.time()
        log.info(f"Task {task_id} finished processing. Final DB status: '{final_task_status}'. Duration: {end_time - start_time:.2f}s")


def run_worker_loop(sleep_interval=15):
    """Main worker loop to fetch and process pending tasks continuously."""
    log.info("WORKER LOOP: Starting run_worker_loop function...")
    cycle_count = 0

    while True:
        cycle_count += 1
        log.info(f"WORKER LOOP: Cycle {cycle_count} - Top of loop.")

        tasks_processed_this_cycle = 0
        pending_tasks = []

        try:
            log.info(f"WORKER LOOP: Cycle {cycle_count} - Calling get_pending_tasks...")
            tasks_limit = 1 # Process one task per cycle
            pending_tasks = database.get_pending_tasks(limit=tasks_limit)
            log.info(f"WORKER LOOP: Cycle {cycle_count} - get_pending_tasks returned {len(pending_tasks)} task(s).")

            if pending_tasks:
                task_to_process = pending_tasks[0]
                log.info(f"WORKER LOOP: Cycle {cycle_count} - Processing task ID: {task_to_process.get('task_id', 'N/A')}")
                process_single_task(task_to_process)
                tasks_processed_this_cycle += 1
                log.info(f"WORKER LOOP: Cycle {cycle_count} - Finished processing attempt for task.")
            else:
                log.info(f"WORKER LOOP: Cycle {cycle_count} - No pending tasks found.")

        except Exception as e:
            log.exception(f"WORKER LOOP: Cycle {cycle_count} - Critical error in main loop execution: {e}")
            # Optional: Add a longer sleep after a critical error
            # time.sleep(60)

        # Wait before the next cycle
        try:
            jitter = random.uniform(-sleep_interval * 0.1, sleep_interval * 0.1)
            actual_sleep = max(5, sleep_interval + jitter)
            log.info(f"WORKER LOOP: Cycle {cycle_count} - Sleeping for {actual_sleep:.2f} seconds...")
            time.sleep(actual_sleep)
            # log.info(f"WORKER LOOP: Cycle {cycle_count} - Woke up from sleep.") # Can be noisy
        except KeyboardInterrupt:
             log.info("KeyboardInterrupt received. Stopping worker loop.")
             break
        except Exception as sleep_err:
             log.error(f"WORKER LOOP: Cycle {cycle_count} - Error during sleep: {sleep_err}. Sleeping for default interval.")
             time.sleep(sleep_interval)


# --- Main Execution ---
if __name__ == "__main__":
    log.info("WORKER SCRIPT: Starting execution (__name__ == '__main__').")
    # Ensure the necessary service __init__ methods expect individual args where needed
    run_worker_loop()
    log.info("WORKER SCRIPT: Exited run_worker_loop.")