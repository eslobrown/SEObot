import os
import logging
from datetime import datetime, timedelta
import pandas as pd
import mysql.connector
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow # <--- Need this
from google.auth.transport.requests import Request # <--- Need this
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# Make sure config is imported if needed directly, or passed via __init__
# from config import GOOGLE_CONFIG # Example if needed directly

class SearchConsoleAPI:
    """Handles Google Search Console authentication and basic data fetching."""

    # Modify __init__ to accept config paths from the main config object
    def __init__(self, client_secrets_file_path, token_file_path, site_url, scopes=['https://www.googleapis.com/auth/webmasters.readonly']):
        self.client_secrets_file = client_secrets_file_path # Use the specific path
        self.token_file = token_file_path # Use the specific path
        self.site_url = site_url
        self.scopes = scopes
        self.credentials = None
        self.service = None
        logging.info(f"Initializing SearchConsoleAPI for site: {self.site_url}")

    def authenticate(self):
        """Authenticate with Google Search Console API using OAuth Installed App Flow."""
        self.credentials = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        try:
            if os.path.exists(self.token_file):
                self.credentials = Credentials.from_authorized_user_file(self.token_file, self.scopes)
                logging.info(f"Loaded credentials from {self.token_file}")
            # If there are no (valid) credentials available, let the user log in.
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    logging.info("Refreshing expired GSC credentials...")
                    try:
                        self.credentials.refresh(Request())
                        logging.info("Credentials refreshed successfully.")
                    except Exception as refresh_err:
                         # If refresh fails (e.g., token revoked), need to re-authenticate
                         logging.error(f"Failed to refresh token: {refresh_err}. Need re-authentication.")
                         self.credentials = None # Force re-auth flow
                else:
                     self.credentials = None # Ensure we trigger the flow if no valid creds

                # Only run the flow if credentials are still None (missing or failed refresh)
                if not self.credentials:
                    logging.info("GSC credentials not found or invalid, initiating OAuth flow.")
                    if not os.path.exists(self.client_secrets_file):
                         raise FileNotFoundError(f"Client secrets file not found at: {self.client_secrets_file}")

                    flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
                    # --- IMPORTANT ---
                    # This flow CANNOT run non-interactively on PythonAnywhere directly
                    # if token.json is missing or invalid. It must be run locally first
                    # to generate the initial token.json.
                    # We add a check here to prevent the server from hanging.
                    if "PYTHONANYWHERE_DOMAIN" in os.environ: # Check if running on PA
                         logging.error("Cannot run interactive OAuth flow on PythonAnywhere.")
                         logging.error(f"Please generate '{self.token_file}' locally and upload it.")
                         raise RuntimeError("Interactive OAuth flow required but cannot run on server.")
                    else:
                         # This part runs locally to get the token the first time
                         logging.warning("Attempting to run local server for OAuth flow. Requires browser interaction.")
                         self.credentials = flow.run_local_server(port=0)
                         logging.info("OAuth flow completed locally.")


            # Save the credentials for the next run (even after refresh)
            # Check if credentials object exists before trying to save
            if self.credentials:
                try:
                    with open(self.token_file, 'w') as token:
                        token.write(self.credentials.to_json())
                    logging.info(f"GSC credentials saved/updated in {self.token_file}")
                except Exception as save_err:
                    logging.error(f"Failed to save token file {self.token_file}: {save_err}")
                    # Proceed without saving, but log the error
            else:
                 # This case happens if refresh failed AND we are on PA preventing new flow
                 raise ConnectionAbortedError("Could not obtain valid GSC credentials.")


            # Build the service object
            self.service = build('searchconsole', 'v1', credentials=self.credentials)
            logging.info('Successfully authenticated with Google Search Console')
            return True

        except FileNotFoundError as fnf_err:
             logging.error(f"Authentication failed: {fnf_err}")
             raise
        except RuntimeError as rt_err: # Catch the specific error for running flow on PA
             logging.error(f"Authentication failed: {rt_err}")
             raise
        except ConnectionAbortedError as ca_err:
             logging.error(f"Authentication failed: {ca_err}")
             raise
        except Exception as e:
            logging.error(f'GSC Authentication failed: {str(e)}', exc_info=True) # Log traceback
            raise # Re-raise other exceptions

    def verify_site_access(self):
        """Verify access to the configured site URL."""
        if not self.service:
            logging.error("Authentication needed before verifying site access.")
            return False
        try:
            sites = self.service.sites().list().execute()
            available_sites = [site['siteUrl'] for site in sites.get('siteEntry', [])]
            if self.site_url not in available_sites:
                logging.error(f"Site {self.site_url} not found in GSC account. Available: {available_sites}")
                return False
            logging.info(f"Successfully verified access to {self.site_url}")
            return True
        except HttpError as e:
            logging.error(f"Failed to verify site access (API Error): {e.resp.status} - {e.content}")
            return False
        except Exception as e:
            logging.error(f"Failed to verify site access: {str(e)}")
            return False

    def get_search_analytics_data(self, days=30, start_row=0, row_limit=25000):
        """Fetch search analytics data for the configured site."""
        if not self.service:
            logging.error("Authentication needed before fetching data.")
            return None

        try:
            end_date = datetime.now() - timedelta(days=3) # GSC data delay
            start_date = end_date - timedelta(days=days)

            request = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['query', 'date'], # Keeping date dimension for potential trend analysis
                'rowLimit': row_limit,
                'startRow': start_row,
                'dataState': 'all' # Fetch all data including fresh data
            }

            response = self.service.searchanalytics().query(
                siteUrl=self.site_url,
                body=request
            ).execute()

            logging.info(f"Fetched {len(response.get('rows', []))} rows from GSC starting at row {start_row}.")
            return response

        except HttpError as e:
             logging.error(f"Failed to fetch search data (API Error): {e.resp.status} - {e.content}")
             # Consider specific error handling (e.g., 403 permission denied)
             raise
        except Exception as e:
            logging.error(f'Failed to fetch search data: {str(e)}')
            raise
        return None

class SearchConsoleDataProcessor:
    """Handles processing and storing Search Console data into MySQL."""

    def __init__(self, db_connection_func):
        """
        Args:
            db_connection_func (callable): A function that returns a MySQL connection object.
        """
        self.get_db_connection = db_connection_func
        logging.info("Initializing SearchConsoleDataProcessor.")

    def _get_connection_cursor(self):
        """Gets a MySQL connection and cursor."""
        conn = self.get_db_connection()
        if not conn:
            raise ConnectionError("Failed to establish database connection.")
        cursor = conn.cursor()
        return conn, cursor

    def save_search_data(self, gsc_response):
        """Saves fetched GSC data to the MySQL database."""
        if not gsc_response or 'rows' not in gsc_response:
            logging.warning('No GSC data rows to save.')
            return 0

        conn = None
        cursor = None
        saved_count = 0
        try:
            conn, cursor = self._get_connection_cursor()
            insert_query = """
                INSERT INTO search_data (query, date, clicks, impressions, ctr, position)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    clicks = VALUES(clicks),
                    impressions = VALUES(impressions),
                    ctr = VALUES(ctr),
                    position = VALUES(position)
            """
            # Using ON DUPLICATE KEY UPDATE handles inserts and updates efficiently

            data_to_insert = []
            min_date_str = '9999-12-31'
            max_date_str = '0000-01-01'

            for row in gsc_response['rows']:
                query = row['keys'][0]
                date_str = row['keys'][1]
                min_date_str = min(min_date_str, date_str)
                max_date_str = max(max_date_str, date_str)

                data_to_insert.append((
                    query,
                    date_str,
                    row['clicks'],
                    row['impressions'],
                    row['ctr'],
                    row['position']
                ))

            if data_to_insert:
                 # Optional: Delete data for the specific date range first if ON DUPLICATE KEY isn't sufficient
                 # delete_query = "DELETE FROM search_data WHERE date BETWEEN %s AND %s"
                 # cursor.execute(delete_query, (min_date_str, max_date_str))
                 # logging.info(f"Deleted existing data between {min_date_str} and {max_date_str}.")

                cursor.executemany(insert_query, data_to_insert)
                conn.commit()
                saved_count = cursor.rowcount # Note: rowcount might be tricky with ON DUPLICATE
                logging.info(f'Successfully saved/updated {len(data_to_insert)} rows ({saved_count} affected) to MySQL database.')

        except mysql.connector.Error as err:
            logging.error(f"Database error during save: {err}")
            if conn:
                conn.rollback()
            raise # Re-raise to signal failure
        except Exception as e:
            logging.error(f'Failed to save GSC data to database: {str(e)}')
            if conn:
                conn.rollback()
            raise # Re-raise to signal failure
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
        return len(data_to_insert) # Return number attempted

    def get_aggregated_data(self, min_impressions=100):
         """Fetches aggregated data from the MySQL database."""
         conn = None
         cursor = None
         try:
             conn, cursor = self._get_connection_cursor()
             # MySQL uses %s placeholders
             query = """
                 SELECT
                     query,
                     AVG(position) as avg_position,
                     SUM(impressions) as total_impressions,
                     SUM(clicks) as total_clicks,
                     -- Ensure safe division, default to 0 if impressions are 0
                     COALESCE(SUM(clicks) / NULLIF(SUM(impressions), 0), 0) as avg_ctr
                 FROM search_data
                 GROUP BY query
                 HAVING SUM(impressions) >= %s
                 ORDER BY total_impressions DESC
             """
             cursor.execute(query, (min_impressions,))
             # Fetch data into a pandas DataFrame
             df = pd.DataFrame(cursor.fetchall(), columns=[i[0] for i in cursor.description])
             logging.info(f"Retrieved {len(df)} aggregated queries with >= {min_impressions} impressions.")
             return df

         except mysql.connector.Error as err:
             logging.error(f"Database error fetching aggregated data: {err}")
             return pd.DataFrame() # Return empty DataFrame on error
         except Exception as e:
             logging.error(f"Error fetching aggregated data: {str(e)}")
             return pd.DataFrame()
         finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    # --- Add other query methods from SearchConsoleAnalyzer, adapting SQL ---

    def get_position_distribution(self):
        """Get distribution of average positions from MySQL."""
        conn = None
        cursor = None
        try:
            conn, cursor = self._get_connection_cursor()
            query = """
                SELECT
                    CASE
                        WHEN avg_position <= 3 THEN 'Top 3'
                        WHEN avg_position <= 10 THEN 'Top 10'
                        WHEN avg_position <= 20 THEN 'Top 20'
                        ELSE '20+'
                    END as position_range,
                    COUNT(*) as query_count
                FROM (
                    SELECT
                        query,
                        AVG(position) as avg_position
                    FROM search_data
                    GROUP BY query
                ) as avg_pos_subquery
                GROUP BY position_range
                ORDER BY
                    FIELD(position_range, 'Top 3', 'Top 10', 'Top 20', '20+')
            """ # Using FIELD for custom sort order in MySQL
            cursor.execute(query)
            df = pd.DataFrame(cursor.fetchall(), columns=[i[0] for i in cursor.description])
            logging.info("Retrieved position distribution data.")
            return df
        except mysql.connector.Error as err:
            logging.error(f"Database error getting position distribution: {err}")
            return pd.DataFrame()
        except Exception as e:
            logging.error(f'Failed to get position distribution: {str(e)}')
            return pd.DataFrame()
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()

    def get_query_trends(self, top_n=20):
        """Analyze query trends over time from MySQL."""
        conn = None
        cursor = None
        try:
            conn, cursor = self._get_connection_cursor()
            # MySQL uses LIMIT clause at the end
            query = """
                WITH query_stats AS (
                    SELECT
                        query,
                        date,
                        position,
                        impressions,
                        clicks
                    FROM search_data
                ),
                query_metrics AS (
                    SELECT
                        query,
                        AVG(position) as current_position,
                        SUM(impressions) as total_impressions,
                        SUM(clicks) as total_clicks,
                        MIN(position) as best_position,
                        MAX(position) as worst_position
                    FROM query_stats
                    GROUP BY query
                    HAVING SUM(impressions) >= 20 -- Use SUM(impressions) here
                )
                SELECT
                    query,
                    ROUND(current_position, 2) as current_position,
                    total_impressions,
                    total_clicks,
                    ROUND(best_position, 2) as best_position,
                    ROUND(worst_position, 2) as worst_position,
                    ROUND(worst_position - best_position, 2) as position_volatility
                FROM query_metrics
                ORDER BY total_impressions DESC
                LIMIT %s
            """
            cursor.execute(query, (top_n,))
            df = pd.DataFrame(cursor.fetchall(), columns=[i[0] for i in cursor.description])
            logging.info(f"Retrieved query trends for top {top_n} queries.")
            return df
        except mysql.connector.Error as err:
            logging.error(f"Database error getting query trends: {err}")
            return pd.DataFrame()
        except Exception as e:
            logging.error(f'Failed to get query trends: {str(e)}')
            return pd.DataFrame()
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()