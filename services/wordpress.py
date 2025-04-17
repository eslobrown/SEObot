import os
import logging
import requests
import json
import mysql.connector
from io import BytesIO
from urllib.parse import urlparse
from typing import Optional

# Configure root logger (optional, but fine if kept)
# Get a specific logger for this module
log = logging.getLogger(__name__)

class WordPressService:
    def __init__(self, api_url, api_user, api_password, db_connection_func=None):
            # --- MODIFICATION START ---
        # Ensure api_url points to the REST API root, typically ending in /wp-json/
        if api_url:
            # Remove trailing slashes and specific namespaces like /wp/v2 if present
            temp_url = api_url.rstrip('/')
            if temp_url.endswith('/wp/v2'):
                self.api_url_base = temp_url[:-len('/wp/v2')].rstrip('/') # Get the part before /wp/v2
            elif temp_url.endswith('/wc/v3'):
                 self.api_url_base = temp_url[:-len('/wc/v3')].rstrip('/') # Get the part before /wc/v3
            else:
                 # Assume it might already be the root or just needs /wp-json check
                 if not temp_url.endswith('/wp-json'):
                      # If it doesn't end with /wp-json, log a warning, but proceed
                      # It's better if the config URL is explicitly the /wp-json URL
                      log.warning(f"Provided API URL '{api_url}' does not end with /wp-json. Assuming it's the base REST API URL.")
                      self.api_url_base = temp_url
                 else:
                      self.api_url_base = temp_url # It already ends with /wp-json
        else:
            self.api_url_base = None
        # --- MODIFICATION END ---

        self.api_user = api_user
        self.api_password = api_password
        self.get_db_connection = db_connection_func
        self.auth = (self.api_user, self.api_password)

        if not db_connection_func:
             log.warning("No database connection function provided to WordPressService. DB operations will fail.")

        # Extract base site URL for convenience
        self.base_site_url = ""
        if api_url:
             try:
                 # Try to intelligently find the part before /wp-json if present
                 if '/wp-json' in api_url:
                     self.base_site_url = api_url.split('/wp-json')[0].rstrip('/')
                 else:
                     # Assume the provided URL might be the base if /wp-json is missing
                     parsed = urlparse(api_url)
                     self.base_site_url = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
                 log.info(f"Determined base site URL: {self.base_site_url}")
             except Exception as e:
                  log.error(f"Could not parse base site URL from API URL '{api_url}': {e}")

        # Validation check
        if not self.api_url_base or not self.api_user or not self.api_password:
            raise ValueError("API URL (pointing to /wp-json/), User, and Password are required for WordPressService.")

        log.info(f"WordPressService initialized for API base: {self.api_url_base}") # Log the adjusted base

        # --- NEW: update_term_meta ---
    def update_term_meta(self, term_id: int, meta_key: str, meta_value: str) -> bool:
        """Updates (or adds) term meta using a direct database connection."""
        if not self.get_db_connection:
            log.error("Cannot update term meta: Database connection function not provided.")
            return False
        if not term_id or not meta_key:
             log.error("Cannot update term meta: term_id and meta_key are required.")
             return False
        # Allow meta_value to be None or empty string for deletion/clearing purposes
        # if meta_value is None: meta_value = '' # Treat None as empty string for DB

        conn = None
        cursor = None
        success = False
        wp_prefix = os.getenv('WP_TABLE_PREFIX', 'wp_') # Get prefix from env

        try:
            log.info(f"Attempting to update term meta for term_id={term_id}, meta_key='{meta_key}'")
            conn = self.get_db_connection()
            if not conn:
                log.error("Failed to get DB connection for term meta update.")
                return False

            cursor = conn.cursor()

            # Use INSERT ... ON DUPLICATE KEY UPDATE for atomicity
            # This simplifies logic (no need to check existence first)
            # Assumes meta_id is the primary key or there's a unique key on (term_id, meta_key)
            # If using standard WP schema, a unique key usually exists.
            sql = f"""
                INSERT INTO {wp_prefix}termmeta (term_id, meta_key, meta_value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value)
            """
            cursor.execute(sql, (term_id, meta_key, meta_value))
            log.debug(f"Executed INSERT/UPDATE for term meta term_id={term_id}, meta_key='{meta_key}'")

            conn.commit()
            # Check rowcount: 1 means insert, 2 means update (usually), 0 means no change/error
            if cursor.rowcount > 0:
                 success = True
                 log.info(f"Successfully updated/inserted term meta for term_id={term_id}, meta_key='{meta_key}' (Rows affected: {cursor.rowcount})")
            elif cursor.rowcount == 0:
                 # This could mean the value was already the same. Treat as success for workflow.
                 success = True
                 log.info(f"Term meta value likely unchanged for term_id={term_id}, meta_key='{meta_key}'.")
            else:
                 # Should not happen with INSERT...ON DUPLICATE KEY UPDATE unless there's an error caught below
                 success = False


        except mysql.connector.Error as err:
            log.error(f"Database error updating term meta for term_id={term_id}, meta_key='{meta_key}': {err}")
            if conn: conn.rollback()
            success = False
        except Exception as e:
            log.error(f"Unexpected error updating term meta for term_id={term_id}, meta_key='{meta_key}': {e}", exc_info=True)
            if conn: conn.rollback()
            success = False
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        return success
    # --- END NEW ---

        # --- NEW: get_term_link ---
    def get_term_link(self, term_id: int, taxonomy: str) -> Optional[str]:
        """Gets the public URL for a taxonomy term using database."""
        if not term_id or not taxonomy:
            log.error("term_id and taxonomy are required to get term link.")
            return None
        if not self.get_db_connection:
            log.error("Cannot get term link: Database connection function not provided.")
            return None
        if not self.base_site_url:
             log.warning("Base site URL not determined, cannot construct term link.")
             return None

        conn = None
        cursor = None
        link = None
        wp_prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

        try:
            log.debug(f"Attempting to get link for term_id={term_id}, taxonomy='{taxonomy}'")
            conn = self.get_db_connection()
            if not conn:
                 log.error("Failed to get DB connection for term link.")
                 return None

            cursor = conn.cursor(dictionary=True)

            query = f"""
                SELECT t.slug
                FROM {wp_prefix}terms AS t
                INNER JOIN {wp_prefix}term_taxonomy AS tt ON t.term_id = tt.term_id
                WHERE t.term_id = %s AND tt.taxonomy = %s
            """
            cursor.execute(query, (term_id, taxonomy))
            result = cursor.fetchone()

            if result and result.get('slug'):
                slug = result['slug']
                # Construct the URL based on common WordPress structures
                if taxonomy == 'category':
                    link = f"{self.base_site_url}/category/{slug}/"
                elif taxonomy == 'post_tag':
                    link = f"{self.base_site_url}/tag/{slug}/"
                elif taxonomy == 'product_cat':
                     link = f"{self.base_site_url}/product-category/{slug}/" # Common WC structure
                elif taxonomy == 'product_tag':
                     link = f"{self.base_site_url}/product-tag/{slug}/" # Common WC structure
                else:
                    # Fallback for other custom taxonomies
                    link = f"{self.base_site_url}/{taxonomy}/{slug}/"
                log.info(f"Constructed link for term_id={term_id}: {link}")
            else:
                log.warning(f"Could not find slug for term_id={term_id}, taxonomy='{taxonomy}'. Cannot generate link.")

        except mysql.connector.Error as err:
            log.error(f"Database error getting term link for term_id={term_id}: {err}")
        except Exception as e:
            log.error(f"Unexpected error getting term link for term_id={term_id}: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        return link
    # --- END NEW ---

    def _make_request(self, method, endpoint, params=None, data=None, json_data=None, files=None, headers=None):
        """Helper function to make authenticated requests to the WP REST API."""
        # --- MODIFICATION START ---
        # Expect endpoint to include the namespace, e.g., "wp/v2/posts" or "wc/v3/products/categories"
        if not self.api_url_base:
             log.error("Cannot make request: WordPress API base URL is not configured.")
             return None

        url = f"{self.api_url_base}/{endpoint.lstrip('/')}"
        # --- MODIFICATION END ---

        req_headers = headers if headers else {}
        if json_data and 'Content-Type' not in req_headers:
             req_headers['Content-Type'] = 'application/json'

        log.debug(f"Making WP Request: {method} {url}")

        try:
            response = requests.request(
                method,
                url,
                params=params,
                data=data,
                json=json_data,
                files=files,
                auth=self.auth,
                headers=req_headers,
                timeout=30
            )
            response.raise_for_status()
            if response.content:
                 # Check for JSON content type before decoding
                 if 'application/json' in response.headers.get('Content-Type', ''):
                     return response.json()
                 else:
                     log.warning(f"Received non-JSON response from {url}. Status: {response.status_code}. Content-Type: {response.headers.get('Content-Type')}")
                     return response.text # Return text if not JSON
            else:
                 return {}
        except requests.exceptions.Timeout:
             log.error(f"Request timed out: {method} {url}")
             return None
        except requests.exceptions.HTTPError as e:
             error_content = "No error content."
             try:
                   if e.response is not None and e.response.content:
                       if 'application/json' in e.response.headers.get('Content-Type', ''):
                           error_content = e.response.json()
                       else:
                           error_content = e.response.text
             except Exception: # Broad exception during error handling
                   if e.response is not None:
                       error_content = e.response.text
             log.error(f"HTTP error: {e.response.status_code} calling {method} {url}. Response: {error_content}")
             # Optionally return the error response details
             # return {'error': True, 'status_code': e.response.status_code, 'response': error_content}
             return None
        except requests.exceptions.RequestException as e:
            log.error(f"Request failed: {method} {url} - {e}")
            return None
        except Exception as e:
             log.error(f"Unexpected error during request: {method} {url} - {e}")
             return None

    def upload_image(self, image_data: BytesIO, title, filename):
        """Uploads an image to the WordPress Media Library."""
        endpoint = 'wp/v2/media' # Prepend namespace
        image_data.seek(0)
        files = {'file': (filename, image_data, 'image/jpeg')}
        img_data = {'title': title, 'alt_text': title, 'caption': title}
        log.info(f"Uploading image '{filename}' to WordPress...")
        response_data = self._make_request('POST', endpoint, data=img_data, files=files)
        if response_data and isinstance(response_data, dict) and 'id' in response_data: # Check type before accessing 'id'
            log.info(f"Image uploaded successfully. Attachment ID: {response_data['id']}")
            return response_data['id']
        else:
            log.error(f"Failed to upload image. Response: {response_data}")
            return None

    def create_post(self, post_data, rest_base):
        """Creates a new post using its REST base."""
        if not rest_base:
            log.error("rest_base cannot be empty when creating content.")
            return None
        endpoint = f'wp/v2/{rest_base}' # Prepend default namespace
        log.info(f"Attempting to create WordPress content via REST base '{rest_base}' with title: {post_data.get('title', 'Untitled')}")
        log.debug(f"Using endpoint: {endpoint}") # Log the full endpoint path
        return self._make_request('POST', endpoint, json_data=post_data)

    # --- update_post uses rest_base ---
    def update_post(self, post_id, update_data, rest_base): # Use rest_base
        """Updates an existing post using its REST base."""
        endpoint = f'wp/v2/{rest_base}/{post_id}' # Prepend default namespace
        log.info(f"Updating WordPress content via REST base '{rest_base}' ID: {post_id}")
        return self._make_request('POST', endpoint, json_data=update_data)

    # --- get_post uses rest_base ---
    def get_post(self, post_id, rest_base): # Use rest_base
        """Retrieves a post by ID using its REST base."""
        endpoint = f'wp/v2/{rest_base}/{post_id}' # Prepend default namespace
        return self._make_request('GET', endpoint)

    # --- check_content_exists uses rest_base ---
    def check_content_exists(self, keyword, rest_base): # Use rest_base
        """Checks if content related to a keyword already exists via REST base."""
        endpoint = f'wp/v2/{rest_base}' # Prepend default namespace
        params = {'search': keyword, 'per_page': 1, '_fields': 'id,title', 'status': 'any'}
        log.debug(f"Checking existence for keyword '{keyword}' via REST base '{rest_base}' using endpoint '{endpoint}'")
        results = self._make_request('GET', endpoint, params=params)

        if results is None:
             log.warning(f"API call failed or returned None while checking existence for '{keyword}' via REST base '{rest_base}'. Assuming not found.") # Update log message
             return False

        if isinstance(results, list) and len(results) > 0:
            log.info(f"Found existing content via REST base '{rest_base}' potentially related to '{keyword}': ID {results[0].get('id')}") # Update log message
            return True
        else:
             log.debug(f"No existing content found via REST base '{rest_base}' search for '{keyword}'.") # Update log message
             return False

    # --- Add methods for category updates, meta updates etc. as needed ---
    # Example:
    # def update_category_meta(self, category_id, meta_key, meta_value):
    #     # This might require direct DB access or a specific plugin endpoint
    #     # if core REST API doesn't support term meta easily.
    #     logging.warning("update_category_meta via REST API might be limited. Consider direct DB or custom endpoint.")
    #     # Placeholder for direct DB approach:
    #     if not self.get_db_connection:
    #         logging.error("DB connection function not provided for category meta update.")
    #         return False
    #     conn = None
    #     cursor = None
    #     try:
    #         # ... (DB update logic using self.get_db_connection) ...
    #         pass
    #     except Exception as e:
    #          logging.error(f"Failed to update category meta via DB: {e}")
    #          return False
    #     finally:
    #          # ... (Close cursor and connection) ...
    #          pass