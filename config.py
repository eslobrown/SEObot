# config.py
import os
from dotenv import load_dotenv, find_dotenv
# import logging # Disable standard logging for this test
import sys
from datetime import datetime

# --- Simple File Logger ---
CONFIG_LOG_FILE = '/home/eslobrown/seobot/config_debug.log' # Log file in your project dir

def simple_log(message):
    """Appends a message with timestamp to the log file."""
    try:
        # Use 'a' to append
        with open(CONFIG_LOG_FILE, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {message}\n")
    except Exception as e:
        # Fallback to stderr if file logging fails
        print(f"FILE LOGGING FAILED: {e}", file=sys.stderr)
        print(f"Original Message: {message}", file=sys.stderr)
# --- End Simple File Logger ---


# --- Debugging python-dotenv ---
simple_log(f"--- Starting config.py ---")
simple_log(f"Current working directory: {os.getcwd()}")

expected_dotenv_path = os.path.join('/home/eslobrown/seobot', '.env')
simple_log(f"Expected .env path: {expected_dotenv_path}")

loaded = False
if os.path.exists(expected_dotenv_path):
    simple_log(".env file EXISTS at expected path.")
    try:
        loaded = load_dotenv(dotenv_path=expected_dotenv_path, override=True, verbose=False) # verbose=False now
        simple_log(f"load_dotenv(path='{expected_dotenv_path}') returned: {loaded}")
        if not loaded:
             simple_log("WARNING: load_dotenv returned False.")
    except Exception as e_load:
        simple_log(f"ERROR during load_dotenv execution: {e_load}")
        loaded = False
else:
    simple_log(f"ERROR: .env file NOT FOUND at expected path: {expected_dotenv_path}")
    found_by_find = find_dotenv(raise_error_if_not_found=False)
    simple_log(f"WARNING: find_dotenv() located .env at: {found_by_find}")

wp_url_check = os.getenv('WP_API_URL')
db_host_check = os.getenv('DB_HOST')
secret_check = os.getenv('WP_PLUGIN_SECRET_TOKEN')
client_secrets_check = os.getenv('GOOGLE_CLIENT_SECRETS_FILE')
token_file_check = os.getenv('GOOGLE_TOKEN_FILE')

simple_log(f"Post-load check: WP_API_URL = {wp_url_check}")
simple_log(f"Post-load check: DB_HOST = {db_host_check}")
simple_log(f"Post-load check: WP_PLUGIN_SECRET_TOKEN = {secret_check}")
simple_log(f"Post-load check: GOOGLE_CLIENT_SECRETS_FILE = {client_secrets_check}")
simple_log(f"Post-load check: GOOGLE_TOKEN_FILE = {token_file_check}")
simple_log(f"--- End .env Debugging ---")
# --- End Debugging ---

# --- !!! ADD CPT SLUG CONSTANT !!! ---
ACB_POST_TYPE_SLUG = 'acb_content_brief'
ACB_REST_BASE = 'content-briefs'         # Use the REST base for API calls
# --- End CPT Slug Constant ---

# --- Essential Configurations ---
# ... (Keep all os.getenv calls and dictionary definitions) ...
FLASK_APP_SECRET_KEY = os.getenv('FLASK_APP_SECRET_KEY', 'generate_a_strong_secret_key_please')
WP_PLUGIN_SECRET_TOKEN = os.getenv('WP_PLUGIN_SECRET_TOKEN')
WP_CONFIG = {
    'api_url': os.getenv('WP_API_URL'),
    'api_user': os.getenv('WP_API_USER'),
    'api_password': os.getenv('WP_API_APP_PASSWORD'),
    'callback_url': os.getenv('WP_PLUGIN_CALLBACK_URL')
}
GOOGLE_CONFIG = { # Revert to OAuth check
    'search_api_key': os.getenv('GOOGLE_SEARCH_API_KEY'),
    'cse_id': os.getenv('GOOGLE_CSE_ID'),
    'client_secrets_file': os.getenv('GOOGLE_CLIENT_SECRETS_FILE'),
    'token_file': os.getenv('GOOGLE_TOKEN_FILE'),
    'gemini_api_key': os.getenv('GEMINI_API_KEY'),
    'gemini_image_model': os.getenv('GEMINI_IMAGE_MODEL', 'imagen-3.0-generate-002')
}
KE_CONFIG = { # ...
    'api_key': os.getenv('KEYWORDS_EVERYWHERE_API_KEY')
}
ANTHROPIC_CONFIG = { # ...
    'api_key': os.getenv('ANTHROPIC_API_KEY'),
    'model': os.getenv('CLAUDE_MODEL', 'claude-3-haiku-20240307'),
    'max_tokens': int(os.getenv('CLAUDE_MAX_TOKENS', '8000')),
    'rate_limit_per_minute': int(os.getenv('CLAUDE_RATE_LIMIT_PER_MINUTE', '50')),
    'max_retries': int(os.getenv('CLAUDE_MAX_RETRIES', '3'))
}
SEARCH_CONSOLE_CONFIG = { # ...
    'site_url': os.getenv('SITE_URL')
}
DATABASE_CONFIG = { # ...
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': 3306
}
WORKER_CONFIG = { # ...
    'max_task_retries': 3,
    'tasks_to_process_per_run': 2
}


# --- Validation Function (using simple_log) ---
def validate_config():
    simple_log("--- Starting validate_config() ---")
    required_wp = ['api_url', 'api_user', 'api_password', 'callback_url']
    required_google = ['client_secrets_file', 'token_file', 'gemini_api_key']
    required_anthropic = ['api_key']
    required_sc = ['site_url']
    required_db = ['host', 'user', 'password', 'database']
    valid = True

    # Check WP_PLUGIN_SECRET_TOKEN
    secret_token_val = WP_PLUGIN_SECRET_TOKEN
    if not secret_token_val:
        simple_log("VALIDATION FAILED: WP_PLUGIN_SECRET_TOKEN is missing or empty.")
        valid = False
    else:
        simple_log(f"VALIDATION CHECK: WP_PLUGIN_SECRET_TOKEN = Present")

    # Check WP Config
    simple_log("--- Checking WP_CONFIG ---")
    for key in required_wp:
        value = WP_CONFIG.get(key)
        if not value:
            simple_log(f"VALIDATION FAILED for WP_CONFIG: {key.upper()} is missing or empty.")
            valid = False
        else:
             simple_log(f"VALIDATION CHECK: WP_CONFIG['{key}'] = Present")

    # Check Google Config
    simple_log("--- Checking GOOGLE_CONFIG ---")
    for key in required_google:
         value = GOOGLE_CONFIG.get(key)
         if not value:
             simple_log(f"VALIDATION FAILED for GOOGLE_CONFIG: {key.upper()} is missing or empty.")
             valid = False
         else:
             simple_log(f"VALIDATION CHECK: GOOGLE_CONFIG['{key}'] = Present")
             if key in ['client_secrets_file']: # Only check existence of client secrets file now
                  file_path = value
                  if not os.path.exists(file_path):
                       simple_log(f"VALIDATION FAILED: File specified by {key.upper()} does not exist at '{file_path}'.")
                       valid = False
                  else:
                       simple_log(f"VALIDATION CHECK: File '{file_path}' exists.")
             elif key == 'token_file' and not os.path.exists(value):
                 simple_log(f"VALIDATION WARNING: Optional file '{value}' for {key.upper()} does not exist.")
             elif key == 'token_file' and os.path.exists(value):
                 simple_log(f"VALIDATION CHECK: Optional file '{value}' exists.")


    # Check Anthropic Config
    simple_log("--- Checking ANTHROPIC_CONFIG ---")
    if not ANTHROPIC_CONFIG.get('api_key'):
         simple_log(f"VALIDATION FAILED for ANTHROPIC_CONFIG: api_key is missing or empty.")
         valid = False
    else:
         simple_log(f"VALIDATION CHECK: ANTHROPIC_CONFIG['api_key'] = Present")

    # Check Search Console Config
    simple_log("--- Checking SEARCH_CONSOLE_CONFIG ---")
    if not SEARCH_CONSOLE_CONFIG.get('site_url'):
         simple_log(f"VALIDATION FAILED for SEARCH_CONSOLE_CONFIG: site_url is missing or empty.")
         valid = False
    else:
         simple_log(f"VALIDATION CHECK: SEARCH_CONSOLE_CONFIG['site_url'] = Present")

    # Check Database Config
    simple_log("--- Checking DATABASE_CONFIG ---")
    for key in required_db:
        value = DATABASE_CONFIG.get(key)
        if not value:
            simple_log(f"VALIDATION FAILED for DATABASE_CONFIG: {key.upper()} is missing or empty.")
            valid = False
        else:
             simple_log(f"VALIDATION CHECK: DATABASE_CONFIG['{key}'] = Present")

    # Final check
    if not valid:
        simple_log("--- Configuration validation failed overall. See previous FAILED messages. ---")
        raise ValueError("Missing critical configuration or files referenced in environment.")
    else:
        simple_log("--- All required configuration variables seem present, validation passed. ---")


# --- Call validation AT THE END ---
try:
    validate_config()
    simple_log("validate_config() completed successfully.")
except ValueError as e:
    simple_log(f"VALIDATION EXCEPTION: {e}") # Log the exception message
    raise # Re-raise to stop execution
except Exception as e_gen:
    simple_log(f"UNEXPECTED EXCEPTION during config validation: {e_gen}")
    raise