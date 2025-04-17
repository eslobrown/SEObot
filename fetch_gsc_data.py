# fetch_gsc_data.py
import os
import logging
from datetime import datetime
import sys
from dotenv import load_dotenv

# --- Load .env Before Other Imports ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
print(f"FETCH_GSC_DATA: Attempting to load .env from: {dotenv_path}", file=sys.stderr)
if os.path.exists(dotenv_path):
    loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
    print(f"FETCH_GSC_DATA: load_dotenv returned: {loaded}", file=sys.stderr)
else:
    print(f"FETCH_GSC_DATA: ERROR - .env file not found at {dotenv_path}", file=sys.stderr)
    sys.exit("FATAL: .env file not found.")
# --- End .env Loading ---

import config # Load configuration AFTER .env is loaded
import database
from services.search_console import SearchConsoleAPI, SearchConsoleDataProcessor

# Configure logging
LOG_FILE = '/home/eslobrown/seobot/fetch_gsc_data.log' # Log file in your project dir
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# --- Main Function ---
def fetch_and_save_gsc_data(days_to_fetch=90, max_rows=25000):
    """Fetches GSC data and saves it to the MySQL database."""
    log.info("--- Starting GSC Data Fetch ---")

    try:
        # 1. Initialize SearchConsoleAPI using config
        log.info("Initializing SearchConsoleAPI...")
        gsc_client = SearchConsoleAPI(
            client_secrets_file_path=config.GOOGLE_CONFIG['client_secrets_file'],
            token_file_path=config.GOOGLE_CONFIG['token_file'],
            site_url=config.SEARCH_CONSOLE_CONFIG['site_url']
        )

        # 2. Authenticate
        log.info("Authenticating with Google Search Console...")
        if not gsc_client.authenticate():
            log.error("GSC Authentication failed. Exiting.")
            return False
        log.info("GSC Authentication successful.")

        # 3. Verify Site Access
        log.info("Verifying site access...")
        if not gsc_client.verify_site_access():
            log.error(f"Access verification failed for site: {gsc_client.site_url}. Exiting.")
            return False
        log.info("Site access verified.")

        # 4. Fetch Data
        log.info(f"Fetching GSC data for the last {days_to_fetch} days (up to {max_rows} rows)...")
        gsc_response = gsc_client.get_search_analytics_data(days=days_to_fetch, row_limit=max_rows)

        if not gsc_response or 'rows' not in gsc_response or not gsc_response['rows']:
            log.warning("No data returned from GSC API for the specified period.")
            # Decide if this is an error or just no data
            # return True # Treat as success if no data is not an error
            return False # Treat as error if data is expected

        log.info(f"Successfully fetched {len(gsc_response.get('rows', []))} rows from GSC.")

        # 5. Initialize Data Processor
        log.info("Initializing SearchConsoleDataProcessor...")
        data_processor = SearchConsoleDataProcessor(database.get_db_connection)

        # 6. Save Data to MySQL
        log.info("Saving fetched data to MySQL database...")
        rows_saved = data_processor.save_search_data(gsc_response)
        log.info(f"Attempted to save/update {rows_saved} rows in the database.")

        log.info("--- GSC Data Fetch Completed Successfully ---")
        return True

    except FileNotFoundError as fnf_err:
        log.error(f"Configuration file error: {fnf_err}. Ensure client_secrets.json and token.json paths are correct.")
        return False
    except RuntimeError as rt_err: # Catch OAuth flow error on server
        log.error(f"OAuth Runtime Error: {rt_err}. Token likely needs regeneration locally.")
        return False
    except ConnectionAbortedError as ca_err:
        log.error(f"GSC Connection Error: {ca_err}. Could not obtain valid credentials.")
        return False
    except Exception as e:
        log.exception(f"An unexpected error occurred during GSC data fetch: {e}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    log.info("Running fetch_gsc_data.py script...")
    success = fetch_and_save_gsc_data(days_to_fetch=90) # Fetch last 90 days
    if success:
        log.info("Script finished successfully.")
        print("GSC data fetch completed successfully.")
        sys.exit(0)
    else:
        log.error("Script finished with errors.")
        print("GSC data fetch failed. Check logs.")
        sys.exit(1)