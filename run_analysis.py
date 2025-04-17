# run_analysis.py - MODIFIED TO REMOVE SCRAPING FUNCTIONALITY & OPTIMIZE CATEGORY FETCHING
import os
import logging
import sys
import json
from dotenv import load_dotenv

# --- Load .env Before Other Imports ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
print(f"RUN_ANALYSIS: Attempting to load .env from: {dotenv_path}", file=sys.stderr)
if os.path.exists(dotenv_path):
    loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
    print(f"RUN_ANALYSIS: load_dotenv returned: {loaded}", file=sys.stderr)
else:
    print(f"RUN_ANALYSIS: ERROR - .env file not found at {dotenv_path}", file=sys.stderr)
    sys.exit("FATAL: .env file not found.")
# --- End .env Loading ---

# --- Configure logging FIRST ---
LOG_FILE = '/home/eslobrown/seobot/run_analysis.log'
try:
    # Basic check if we can write to the directory
    if os.path.exists(LOG_FILE):
        if not os.access(LOG_FILE, os.W_OK):
            print(f"WARNING: Log file {LOG_FILE} exists but is not writable.", file=sys.stderr)
            # Attempt to make it writable (optional, might fail depending on ownership)
            try:
                 os.chmod(LOG_FILE, 0o666)
                 print(f"Attempted chmod 666 on {LOG_FILE}", file=sys.stderr)
            except Exception as chmod_err:
                 print(f"Could not chmod log file: {chmod_err}", file=sys.stderr)
    elif not os.access(os.path.dirname(LOG_FILE), os.W_OK):
         print(f"WARNING: Log directory {os.path.dirname(LOG_FILE)} is not writable.", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO, # Use INFO or DEBUG
        format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, mode='a'), # Use append mode 'a'
            logging.StreamHandler(sys.stdout)
        ]
    )
    log = logging.getLogger(__name__)
    log.info("--- run_analysis.py script started (NO SCRAPING VERSION, OPTIMIZED) ---") # <--- UPDATED LOGGING
    log.info(f"Attempting to log to: {LOG_FILE}")

except Exception as log_err:
    # Fallback if logging setup fails
    print(f"CRITICAL ERROR: Failed to configure logging: {log_err}", file=sys.stderr)
    # Define basic log functions as placeholders if logging fails catastrophically
    class FakeLogger:
        def info(self, msg): print(f"INFO: {msg}", file=sys.stdout)
        def warning(self, msg): print(f"WARNING: {msg}", file=sys.stderr)
        def error(self, msg): print(f"ERROR: {msg}", file=sys.stderr)
        def exception(self, msg): print(f"EXCEPTION: {msg}", file=sys.stderr)
        def debug(self, msg): print(f"DEBUG: {msg}", file=sys.stdout)
    log = FakeLogger()
    log.error(f"Logging failed. Using print statements. Error: {log_err}")

# --- Imports AFTER logging setup ---
import config # Load configuration AFTER .env is loaded
import database
from services.content_analyzer import ContentAnalyzer
from services.wordpress import WordPressService
from services.imagen import ImagenClient # <-- Import ImagenClient
from services.workflow import ContentWorkflowService, safe_get # <--- IMPORT safe_get HERE

# --- Helper Functions ---

def check_brief_exists(wp_service: WordPressService, keyword: str) -> bool:
    """
    Checks if a brief CPT already exists for the given keyword using multiple methods.
    More thorough to prevent duplicate creation.
    """
    try:
        # --- Method 1: Check using the REST API (original method) ---
        rest_base_to_check = config.ACB_REST_BASE
        log.debug(f"Checking if brief exists for keyword: '{keyword}' using REST base: '{rest_base_to_check}'")

        # First try exact match with REST API
        exists = wp_service.check_content_exists(keyword, rest_base=rest_base_to_check)

        if exists:
            log.info(f"Brief check SUCCEEDED: Brief already exists for keyword: '{keyword}' (exact match via API)")
            return True

        # --- Method 2: Try with normalized keywords ---
        # Normalize the search keyword (lowercase, remove punctuation)
        normalized_keyword = keyword.lower().strip()
        normalized_keyword = re.sub(r'[^\w\s]', '', normalized_keyword)

        if normalized_keyword != keyword.lower().strip():
            log.debug(f"Trying normalized keyword: '{normalized_keyword}'")
            exists = wp_service.check_content_exists(normalized_keyword, rest_base=rest_base_to_check)

            if exists:
                log.info(f"Brief check SUCCEEDED: Brief already exists for normalized keyword: '{normalized_keyword}'")
                return True

        # --- Method 3: Check directly in database if possible ---
        if wp_service.get_db_connection:
            conn = None
            cursor = None
            try:
                conn = wp_service.get_db_connection()
                if conn:
                    cursor = conn.cursor(dictionary=True)

                    # Get WordPress table prefix
                    prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

                    # Check title matches with LIKE for case-insensitive comparison
                    query = f"""
                        SELECT ID FROM {prefix}posts p
                        WHERE p.post_type = %s
                        AND (
                            p.post_title LIKE %s
                            OR p.post_title = %s
                            OR p.post_title LIKE %s
                        )
                        AND p.post_status != 'trash'
                        LIMIT 1
                    """

                    # Different variations of the keyword for matching
                    cursor.execute(query, (
                        ACB_POST_TYPE,
                        f"%{keyword}%",  # Partial match
                        keyword,         # Exact match
                        f"{keyword}%"    # Starts with
                    ))

                    result = cursor.fetchone()

                    if result:
                        log.info(f"Brief check SUCCEEDED: Brief already exists for keyword: '{keyword}' (DB title check)")
                        return True

                    # Also check for matches in the _acb_keyword meta field
                    meta_query = f"""
                        SELECT p.ID FROM {prefix}posts p
                        JOIN {prefix}postmeta pm ON p.ID = pm.post_id
                        WHERE p.post_type = %s
                        AND pm.meta_key = '_acb_keyword'
                        AND (
                            pm.meta_value LIKE %s
                            OR pm.meta_value = %s
                            OR pm.meta_value LIKE %s
                        )
                        AND p.post_status != 'trash'
                        LIMIT 1
                    """

                    cursor.execute(meta_query, (
                        ACB_POST_TYPE,
                        f"%{keyword}%",  # Partial match
                        keyword,         # Exact match
                        f"{keyword}%"    # Starts with
                    ))

                    meta_result = cursor.fetchone()

                    if meta_result:
                        log.info(f"Brief check SUCCEEDED: Brief already exists for keyword: '{keyword}' (DB meta check)")
                        return True

            except Exception as db_err:
                log.warning(f"DB check error for '{keyword}': {db_err}")
            finally:
                if cursor:
                    cursor.close()
                if conn and conn.is_connected():
                    conn.close()

        # --- Method 4: API fallback with less strict matching ---
        # Try with partial keyword match if keyword is long enough
        if len(keyword) > 6:
            partial_keyword = keyword.split()[0] if len(keyword.split()) > 1 else keyword[:6]
            log.debug(f"Trying partial keyword: '{partial_keyword}'")

            partial_results = wp_service._make_request(
                'GET',
                f'wp/v2/{rest_base_to_check}',
                params={'search': partial_keyword, 'per_page': 20, '_fields': 'id,title'}
            )

            if isinstance(partial_results, list) and len(partial_results) > 0:
                # Check if any title is very similar to our keyword using fuzzy matching
                for result in partial_results:
                    title = result.get('title', {}).get('rendered', '')
                    if title:
                        # Simple similarity check - if 80% of words match
                        title_words = set(title.lower().split())
                        keyword_words = set(keyword.lower().split())
                        common_words = title_words.intersection(keyword_words)

                        if len(common_words) >= 0.8 * len(keyword_words):
                            log.info(f"Brief check SUCCEEDED: Brief already exists with fuzzy match: '{title}'")
                            return True

        # If we get here, no matching brief was found
        log.info(f"Brief check SUCCEEDED: No existing brief found for keyword: '{keyword}'")
        return False

    except Exception as e:
        # Log the specific error during the check
        log.error(f"Brief check FAILED for '{keyword}': {e}", exc_info=True)

        # IMPORTANT: Decide how to handle check failures.
        # Option 1: Assume it exists to prevent duplicates (safer)
        log.warning(f"Assuming brief exists for '{keyword}' due to check failure.")
        return True
        # Option 2: Assume it doesn't exist (riskier, might cause duplicates if check fails often)
        # return False

def save_brief_to_wp(brief_data: dict, wp_service: WordPressService) -> bool:
    """Maps brief data and saves it as a new CPT in WordPress."""
    if not brief_data or not isinstance(brief_data, dict):
        log.error("Invalid brief_data received for saving to WP.")
        return False

    keyword = brief_data.get('keyword', 'Untitled Brief')
    log.info(f"Preparing to save BRIEF CPT for keyword: '{keyword}' to WordPress...")
    try:
        # --- Separate base post data from meta data ---
        generated_prompt = brief_data.get('claude_prompt', '')
        log.info(f"Prompt length for '{keyword}': {len(generated_prompt)} characters.")
        if not generated_prompt:
            log.warning(f"Claude prompt is EMPTY for keyword '{keyword}'!")
        else:
            log.debug(f"Prompt excerpt for '{keyword}': {generated_prompt[:100]}...")

        # --- Separate base post data from meta data ---
        wp_post_payload = {
            'title': keyword,
            'status': 'publish',
            'content': brief_data.get('notes', ''),
            'comment_status': 'closed',
            'ping_status': 'closed',
            'meta': {
                # --- Required / Always Present Meta ---
                '_acb_keyword': keyword,
                '_acb_search_intent': brief_data.get('search_intent', 'informational'),
                '_acb_claude_prompt': generated_prompt,
                '_acb_status': 'pending',
                '_acb_priority': str(brief_data.get('priority_level', '3')),
                '_acb_notes': brief_data.get('notes', ''),
                '_acb_content_recommendation': brief_data.get('content_recommendation', 'create_new'),
                # --- GSC/KE Data ---
                '_acb_current_position': float(brief_data.get('current_position', 100.0)),
                '_acb_monthly_searches': int(brief_data.get('monthly_searches', 0)),
                '_acb_opportunity_score': float(brief_data.get('opportunity_score', 0.0)),
                '_acb_total_impressions': int(brief_data.get('total_impressions', 0)),
                '_acb_total_clicks': int(brief_data.get('total_clicks', 0)),
                '_acb_avg_ctr': float(brief_data.get('avg_ctr', 0.0)),
                '_acb_cpc': str(brief_data.get('cpc', '$0.00')),
                '_acb_competition': float(brief_data.get('competition', 0.5)),
                # --- Analysis Results ---
                '_acb_target_word_count': int(brief_data.get('target_word_count', 1500)),
                # Initialize other fields as empty strings or appropriate defaults
                '_acb_pa_task_id': '',
                '_acb_error_message': '',
                '_acb_draft_date': '',
                '_acb_published_date': '',
                '_acb_generated_post_id': '', # Keep as empty string initially
                '_acb_generated_post_url': '',
                '_acb_generated_category_url': '',
            }
        }

        # --- Add Optional Numeric/String Meta Conditionally ---
        # Integers - Add only if > 0 or if 0 is meaningful
        monthly_searches = int(brief_data.get('monthly_searches', 0))
        if monthly_searches > 0: wp_post_payload['meta']['_acb_monthly_searches'] = monthly_searches

        target_wc = int(brief_data.get('target_word_count', 0)) # Default 0 if missing
        if target_wc > 0: wp_post_payload['meta']['_acb_target_word_count'] = target_wc
        else: wp_post_payload['meta']['_acb_target_word_count'] = 1500 # Ensure a default value if 0

        total_impressions = int(brief_data.get('total_impressions', 0))
        if total_impressions > 0: wp_post_payload['meta']['_acb_total_impressions'] = total_impressions

        total_clicks = int(brief_data.get('total_clicks', 0))
        if total_clicks > 0: wp_post_payload['meta']['_acb_total_clicks'] = total_clicks

        # Floats/Numbers - Add if not the default value (or always add if 0 is valid)
        current_pos = float(brief_data.get('current_position', 100.0))
        # Always add position, even if 100? Or only if < 100? Let's always add.
        wp_post_payload['meta']['_acb_current_position'] = current_pos

        avg_ctr = float(brief_data.get('avg_ctr', 0.0))
        if avg_ctr > 0.0: wp_post_payload['meta']['_acb_avg_ctr'] = avg_ctr # Only add if > 0

        opp_score = float(brief_data.get('opportunity_score', 0.0))
        if opp_score > 0.0: wp_post_payload['meta']['_acb_opportunity_score'] = opp_score # Only add if > 0

        competition = float(brief_data.get('competition', -1.0)) # Use -1 default to distinguish
        if competition >= 0.0: wp_post_payload['meta']['_acb_competition'] = competition # Add if valid

        # Strings - Add if not empty/default
        cpc = str(brief_data.get('cpc', '$0.00'))
        if cpc != '$0.00': wp_post_payload['meta']['_acb_cpc'] = cpc


        # --- End Conditional Meta ---

        log.debug(f"Calling wp_service.create_post for keyword '{keyword}' with REST base '{config.ACB_REST_BASE}'...")
        log.debug(f"Final Payload Meta (Excerpt): { {k: v for k, v in wp_post_payload['meta'].items() if k != '_acb_claude_prompt'} }") # Log meta except prompt

        result = wp_service.create_post(wp_post_payload, rest_base=config.ACB_REST_BASE)

        if result and result.get('id'):
            log.info(f"Successfully created brief CPT in WordPress for '{keyword}' (ID: {result['id']})")
            return True
        else:
            # Log more details on failure
            status_code = result.get('code', 'N/A') if isinstance(result, dict) else 'N/A'
            message = result.get('message', str(result)) if isinstance(result, dict) else str(result)
            log.error(f"Failed to create brief CPT in WordPress for '{keyword}'. Status: {status_code}, Message: {message}")
            # You might want to inspect the full 'result' object here if errors persist
            # log.debug(f"Full WP API response on failure: {result}")
            return False

    except KeyError as ke:
        log.error(f"Missing expected key in brief_data for keyword '{keyword}': {ke}")
        return False
    except Exception as e:
        log.exception(f"Error saving brief to WordPress for '{keyword}': {e}")
        return False

# --- Helper function to manually create category map for ContentWorkflowService ---
def create_category_mapping(categories):
    """Creates a mapping of lowercase category names/slugs to their data"""
    category_map = {}
    for category in categories:
        cat_id = category.get('id')
        name = category.get('name', '').strip() # Keep original case for display
        name_lower = name.lower()
        slug = category.get('slug', '').lower().strip()
        if cat_id and name and slug:
            category_map[name_lower] = category
            if slug != name_lower:
                category_map[slug] = category
            # Basic plural/singular variations
            if name_lower.endswith('s'):
                singular = name_lower[:-1]
                if singular not in category_map:
                    category_map[singular] = category
            else:
                plural = name_lower + 's'
                if plural not in category_map:
                    category_map[plural] = category
    return category_map

# --- OPTIMIZED MAIN FUNCTION ---
def analyze_and_create_briefs(max_briefs_to_create=50, min_opportunity_score=15):
    """Fetches opportunities, generates briefs, and creates CPTs in WordPress using NO SCRAPING."""
    log.info("--- Starting Opportunity Analysis and Brief Creation (NO SCRAPING VERSION, OPTIMIZED) ---")
    briefs_created_count = 0
    processed_keywords = set() # <-- Add a set to track keywords processed in this run

    try:
        # 1. Initialize Base Services (DB connection implicitly handled)
        log.info("Initializing Base Services (Analyzer, WP, Imagen)...")
        analyzer_config = {
            'KEYWORDS_EVERYWHERE_API_KEY': config.KE_CONFIG.get('api_key'),
            'GOOGLE_SEARCH_API_KEY': config.GOOGLE_CONFIG.get('search_api_key'),
            'GOOGLE_CSE_ID': config.GOOGLE_CONFIG.get('cse_id')
        }
        analyzer = ContentAnalyzer(analyzer_config, database.get_db_connection)

        wp_service = WordPressService(
             api_url=config.WP_CONFIG['api_url'],
             api_user=config.WP_CONFIG['api_user'],
             api_password=config.WP_CONFIG['api_password'],
             db_connection_func=database.get_db_connection
         )

        # Initialize ImagenClient (needed potentially by workflow service later)
        imagen_client = None
        if config.GOOGLE_CONFIG.get('gemini_api_key'):
             imagen_client = ImagenClient(
                 api_key=config.GOOGLE_CONFIG['gemini_api_key'],
                 model=config.GOOGLE_CONFIG.get('gemini_image_model')
             )
        else:
             log.warning("Gemini API Key not found, ImagenClient not initialized.")

        # 2. Initialize ContentWorkflowService (passing other services)
        log.info("Initializing ContentWorkflowService...")
        workflow_service = ContentWorkflowService(
            anthropic_api_key=config.ANTHROPIC_CONFIG['api_key'],
            anthropic_model=config.ANTHROPIC_CONFIG['model'],
            anthropic_max_tokens=config.ANTHROPIC_CONFIG['max_tokens'],
            anthropic_rate_limit=config.ANTHROPIC_CONFIG['rate_limit_per_minute'],
            anthropic_max_retries=config.ANTHROPIC_CONFIG['max_retries'],
            content_analyzer=analyzer, # Pass analyzer instance
            imagen_client=imagen_client, # Pass imagen client instance
            wordpress_service=wp_service # Pass wp service instance
        )
        log.info("Services initialized.")

        # --- OPTIMIZATION: Fetch product categories once at the beginning ---
        log.info("Fetching product categories once for the entire run...")
        product_categories = workflow_service._fetch_site_categories(taxonomy='product_cat')
        if not product_categories:
            log.warning("No product categories found or error fetching categories.")
            product_categories = []

        # Create a mapping of lowercase category names to category data
        category_mapping = create_category_mapping(product_categories)
        log.info(f"Fetched {len(product_categories)} product categories, created mapping with {len(category_mapping)} variations.")
        # --- END OPTIMIZATION ---

        # 3. Get Content Opportunities from DB using Analyzer
        log.info(f"Fetching content opportunities (min score: {min_opportunity_score})...")
        opportunities_df = analyzer.get_content_opportunities(min_impressions=50)

        if opportunities_df.empty:
            log.warning("No content opportunities found matching the criteria.")
            return True

        log.info(f"Found {len(opportunities_df)} potential opportunities from DB.")
        opportunities_df = opportunities_df[opportunities_df['opportunity_score'] >= min_opportunity_score].copy()
        log.info(f"Filtered to {len(opportunities_df)} opportunities with score >= {min_opportunity_score}.")

        if opportunities_df.empty:
            log.info("No opportunities meet the minimum score threshold.")
            return True

        opportunities_df = opportunities_df.sort_values('opportunity_score', ascending=False)
        log.info(f"Processing up to {max_briefs_to_create} top opportunities...")

        for index, row in opportunities_df.iterrows():
            if briefs_created_count >= max_briefs_to_create:
                log.info(f"Reached maximum number of briefs to create ({max_briefs_to_create}). Stopping.")
                break

            keyword = safe_get(row, 'query', f'Unknown_Row_{index}') # Use safe_get

            # --- Add check against keywords processed THIS RUN ---
            if keyword in processed_keywords:
                log.warning(f"Skipping '{keyword}' - Already processed in this run (potential duplicate in source data).")
                continue
            # --- End check ---

            log.info(f"--- Processing Opportunity: '{keyword}' (Score: {safe_get(row, 'opportunity_score', 0.0):.2f}) ---")

            # --- *** REFINED CHECK AND SAVE LOGIC *** ---
            # Perform the check *before* generating the brief data to save resources
            if check_brief_exists(wp_service, keyword):
                 log.info(f"Skipping '{keyword}' - Brief already exists in WordPress (checked via API).")
                 processed_keywords.add(keyword) # Mark as processed even if skipped
                 continue # Skip to the next keyword
            else:
                 # Brief does NOT exist, proceed with generation and saving
                 log.info(f"Brief for '{keyword}' does not exist. Proceeding to generate data...")

                 # --- OPTIMIZATION: Use cached category data ---
                 # This is a bit of a hack, but it avoids adding a new parameter to generate_content_brief
                 # The method will use the cached categories directly without fetching them again
                 row_dict = row.to_dict()
                 row_dict['_cached_categories'] = product_categories
                 row_dict['_cached_category_mapping'] = category_mapping
                 # --- END OPTIMIZATION ---

                 # Generate Full Brief Data using WorkflowService
                 brief_data = workflow_service.generate_content_brief(row_dict)

                 if not brief_data:
                     log.error(f"Failed to generate brief data for '{keyword}'. Skipping saving.")
                     processed_keywords.add(keyword) # Mark as processed even if generation failed
                     continue # Skip to next keyword

                 # Save Brief to WordPress using wp_service
                 log.info(f"Saving brief for '{keyword}' to WordPress...")
                 if save_brief_to_wp(brief_data, wp_service):
                     briefs_created_count += 1
                     log.info(f"Successfully saved brief for '{keyword}'. Count: {briefs_created_count}")
                 else:
                     log.error(f"Failed to save brief for '{keyword}' to WordPress after generation.")
                     # Decide if you want to retry saving or just log the error

                 processed_keywords.add(keyword) # Mark as processed after attempting save
            # --- *** END REFINED CHECK AND SAVE LOGIC *** ---

        log.info(f"--- Analysis and Brief Creation Completed (NO SCRAPING VERSION, OPTIMIZED). Created {briefs_created_count} new briefs. ---")
        return True

    except Exception as e:
        log.exception(f"An unexpected error occurred during analysis and brief creation: {e}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    log.info("Running run_analysis.py __main__ block (NO SCRAPING VERSION, OPTIMIZED)...")
    success = analyze_and_create_briefs(max_briefs_to_create=50, min_opportunity_score=15)
    if success:
        log.info("Script finished successfully (NO SCRAPING VERSION, OPTIMIZED).")
        print("Analysis and brief creation completed successfully using AI fallbacks (NO SCRAPING, OPTIMIZED).")
        sys.exit(0)
    else:
        log.error("Script finished with errors (NO SCRAPING VERSION, OPTIMIZED).")
        print("Analysis and brief creation failed. Check logs.")
        sys.exit(1)