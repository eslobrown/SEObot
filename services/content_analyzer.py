# services/content_analyzer.py
# Modified to remove scraping functionality

import os
import logging
import time
import math
import json
import re
import random
import requests
import pandas as pd
import numpy as np

import nltk
# Import necessary NLTK submodules if not already done globally or handle LookupError
try:
    from nltk.tokenize import word_tokenize
except ImportError:
    nltk.download('punkt')
    from nltk.tokenize import word_tokenize
try:
    from nltk.corpus import stopwords
except ImportError:
     nltk.download('stopwords')
     from nltk.corpus import stopwords
from nltk.util import ngrams
# --- End NLTK ---
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from googleapiclient.discovery import build
from datetime import datetime
import mysql.connector
import config

log = logging.getLogger(__name__)

class ContentAnalyzer:
    """Analyzes competitor content, keywords, and identifies opportunities."""

    def __init__(self, analyzer_config: dict, db_connection_func, wordpress_service=None):
        """
        Args:
            analyzer_config (dict): Dictionary containing required API keys.
                                    Expected keys: KEYWORDS_EVERYWHERE_API_KEY,
                                                   GOOGLE_SEARCH_API_KEY, GOOGLE_CSE_ID
            db_connection_func (callable): Function that returns a MySQL connection.
            wordpress_service (WordPressService, optional): Service for WP interactions.
        """
        self.analyzer_config = analyzer_config
        self.get_db_connection = db_connection_func
        self.wp_service = wordpress_service
        self.batch_size = 100
        self.ke_api_key = self.analyzer_config.get('KEYWORDS_EVERYWHERE_API_KEY')
        self.google_api_key = self.analyzer_config.get('GOOGLE_SEARCH_API_KEY')
        self.google_cse_id = self.analyzer_config.get('GOOGLE_CSE_ID')
        log.debug(f"ContentAnalyzer initialized with KE Key: {'Present' if self.ke_api_key else 'MISSING'}")
        log.debug(f"ContentAnalyzer initialized with Google Search Key: {'Present' if self.google_api_key else 'MISSING'}")
        log.debug(f"ContentAnalyzer initialized with Google CSE ID: {'Present' if self.google_cse_id else 'MISSING'}")
        self._initialize_nltk()
        log.info("ContentAnalyzer initialized.")

    def _initialize_nltk(self):
        """Downloads NLTK resources if not already present, catching LookupError."""
        resources_to_check = {
            'punkt': 'tokenizers/punkt',
            'stopwords': 'corpora/stopwords'
        }
        downloaded_any = False

        for resource_name, resource_path in resources_to_check.items():
            try:
                nltk.data.find(resource_path)
                log.info(f"NLTK resource '{resource_name}' found.")
            except LookupError:
                log.info(f"NLTK resource '{resource_name}' not found. Attempting download...")
                try:
                    nltk.download(resource_name, quiet=True)
                    log.info(f"NLTK resource '{resource_name}' download attempted.")
                    downloaded_any = True
                except Exception as download_err:
                     log.error(f"Failed to download NLTK resource '{resource_name}': {download_err}")

        if downloaded_any:
            time.sleep(1)

        try:
            self.stop_words = set(stopwords.words('english'))
            log.info("NLTK stopwords loaded successfully.")
        except LookupError:
             log.error("NLTK stopwords resource still not available after download attempt!")
             self.stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'in', 'to', 'for', 'of', 'with', 'by', 'at', 'on', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
             log.warning("Using basic fallback stopwords list.")
        except Exception as e:
            log.error(f"Unexpected error loading NLTK stopwords: {e}")
            self.stop_words = set()

    def _get_connection_cursor(self):
        """Gets a MySQL connection and cursor."""
        conn = self.get_db_connection()
        if not conn:
            raise ConnectionError("ContentAnalyzer: Failed to establish database connection.")
        cursor = conn.cursor(dictionary=True)
        return conn, cursor

    # --- Methods using Search Console Data (Now from MySQL) ---

    def get_content_opportunities(self, min_impressions=50):
        """Get content opportunities by combining GSC data and KE data."""
        conn = None
        cursor = None
        try:
            conn, cursor = self._get_connection_cursor()
            query = """
                SELECT
                    query,
                    AVG(position) as avg_position,
                    SUM(impressions) as total_impressions,
                    SUM(clicks) as total_clicks,
                    COALESCE(SUM(clicks) / NULLIF(SUM(impressions), 0), 0) as avg_ctr
                FROM search_data
                GROUP BY query
                HAVING SUM(impressions) >= %s
                ORDER BY total_impressions DESC
            """
            cursor.execute(query, (min_impressions,))
            results = cursor.fetchall()
            if not results:
                 logging.warning(f"No GSC data found matching criteria (min_impressions={min_impressions})")
                 return pd.DataFrame()

            df = pd.DataFrame(results)
            log.info(f"Found {len(df)} GSC queries to analyze from MySQL (min_impressions={min_impressions})")

            ke_data = self.get_keywords_everywhere_data(df['query'].tolist())
            if not ke_data:
                 logging.warning("No Keywords Everywhere data retrieved. Scores will be based on GSC data only.")

            df['monthly_search_volume'] = df['query'].map(lambda x: int(ke_data.get(x, {}).get('search_volume', 0)))
            df['cpc_value'] = df['query'].map(lambda x: float(ke_data.get(x, {}).get('cpc', {'value': '0.00'}).get('value', '0.00')))
            df['competition'] = df['query'].map(lambda x: float(ke_data.get(x, {}).get('competition', 0.0)))
            df['search_trend_json'] = df['query'].map(lambda x: json.dumps(ke_data.get(x, {}).get('trend', [])))

            df['opportunity_score'] = df.apply(
                lambda x: self.calculate_opportunity_score(
                    position=x['avg_position'],
                    impressions=x['monthly_search_volume'] if x['monthly_search_volume'] > 0 else x['total_impressions'],
                    ctr=x['avg_ctr'],
                    competition=x['competition']
                ),
                axis=1
            )

            df['intent'] = df['query'].apply(self.classify_query_intent)

            df = df.sort_values('opportunity_score', ascending=False)
            df = df[df['opportunity_score'] >= 15]

            log.info(f"Generated {len(df)} content opportunities before final filtering.")
            return df

        except mysql.connector.Error as err:
            logging.error(f"Database error getting content opportunities: {err}")
            return pd.DataFrame()
        except Exception as e:
            logging.error(f"Error getting content opportunities: {str(e)}", exc_info=True)
            return pd.DataFrame()
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()

    def calculate_opportunity_score(self, position, impressions, ctr, competition):
        """Calculate content opportunity score."""
        try:
            position = float(position) if position is not None else 30.0
            impressions = int(impressions) if impressions is not None and impressions > 0 else 1
            ctr = float(ctr) if ctr is not None else 0.0
            competition = float(competition) if competition is not None else 0.5

            position_score = max(0.0, (30.0 - position) / 30.0) * 100.0
            capped_impressions = min(impressions, 1000000)
            volume_score = min(math.log10(capped_impressions) * 20.0, 100.0)
            engagement_score = min(ctr * 1000.0, 100.0)
            competition_score = (1.0 - competition) * 100.0

            final_score = (
                (position_score * 0.35) +
                (volume_score * 0.30) +
                (engagement_score * 0.20) +
                (competition_score * 0.15)
            )
            return round(final_score, 2)
        except Exception as e:
            logging.error(f"Error calculating opportunity score: {str(e)}")
            return 0.0

    def classify_query_intent(self, query):
        """Classify query intent."""
        try:
            if not query or not isinstance(query, str): return 'navigational'
            query_lower = query.lower()
            terms = query_lower.split()
            product_patterns = {'buy', 'price', 'cost', 'review', 'best', 'top', 'vs', 'versus', 'compare', 'deal', 'discount', 'shop'}
            info_patterns = {'how', 'what', 'why', 'when', 'where', 'guide', 'tutorial', 'ideas', 'tips', 'ways', 'learn', 'resource', 'example'}
            nav_patterns = {'login', 'account', 'contact', 'about'}

            commercial_score = sum(1 for term in terms if term in product_patterns)
            info_score = sum(1 for term in terms if term in info_patterns)
            nav_score = sum(1 for term in terms if term in nav_patterns)

            if nav_score > 0 and nav_score >= commercial_score and nav_score >= info_score: return 'navigational'
            if commercial_score > info_score:
                 if info_score > 0 and commercial_score <= info_score + 1: return 'informational'
                 return 'commercial'
            if info_score > commercial_score: return 'informational'
            if any(term in query_lower for term in ['review', 'best', 'top', 'vs']): return 'commercial'
            if any(term in query_lower for term in ['how', 'what', 'guide']): return 'informational'
            return 'navigational'
        except Exception as e:
            logging.error(f"Error classifying query intent for '{query}': {str(e)}")
            return 'navigational'

    # --- KE & Google Search API Methods ---

    def get_keywords_everywhere_data(self, queries):
        """Get data from Keywords Everywhere API."""
        if not queries: return {}
        # Use self.ke_api_key initialized in __init__
        if not self.ke_api_key:
            logging.error("Keywords Everywhere API key not configured.")
            return {}

        url = "https://api.keywordseverywhere.com/v1/get_keyword_data"
        headers = {'Authorization': f'Bearer {self.ke_api_key}'}
        all_keyword_data = {}
        processed_count = 0

        for i in range(0, len(queries), self.batch_size):
            batch = queries[i:min(i + self.batch_size, len(queries))]
            logging.info(f"Fetching KE data for batch {i//self.batch_size + 1} ({len(batch)} keywords)")
            data = {'country': 'us', 'currency': 'USD', 'dataSource': 'cli', 'kw[]': batch}

            try:
                response = requests.post(url, headers=headers, data=data, timeout=30)
                response.raise_for_status()
                ke_data = response.json()

                if 'data' in ke_data:
                    for item in ke_data['data']:
                        keyword = item.get('keyword')
                        if keyword:
                            all_keyword_data[keyword] = {
                                'search_volume': item.get('vol', 0),
                                'cpc': item.get('cpc', {'currency': '$', 'value': '0.00'}),
                                'competition': item.get('competition', 0),
                                'trend': item.get('trend', [])
                            }
                            processed_count += 1
                elif 'error' in ke_data:
                     logging.error(f"KE API returned error: {ke_data['error']}")

            except requests.exceptions.RequestException as e:
                logging.error(f"KE API request failed: {str(e)}")
                time.sleep(2)
            except json.JSONDecodeError:
                 logging.error(f"Failed to decode KE API response for batch starting with {batch[0]}")
            except Exception as e:
                 logging.error(f"Unexpected error fetching KE data: {str(e)}")

        logging.info(f"Retrieved KE data for {processed_count} keywords.")
        return all_keyword_data

    def get_top_ranking_urls(self, keyword, num_results=20):
        """Get top ranking URLs using Google Custom Search API."""
        # Use self.google_api_key and self.google_cse_id initialized in __init__
        if not self.google_api_key or not self.google_cse_id:
            logging.error("Google Search API key or CSE ID not configured.")
            return []
        try:
            # Note: Consider caching the service object if called frequently
            service = build("customsearch", "v1", developerKey=self.google_api_key, cache_discovery=False)
            urls = []
            max_per_req = 10
            num_requests = math.ceil(num_results / max_per_req)

            for i in range(num_requests):
                start_index = 1 + (i * max_per_req)
                num_to_fetch = min(max_per_req, num_results - (i * max_per_req))
                if num_to_fetch <= 0: break

                logging.info(f"Fetching Google Search results {start_index}-{start_index+num_to_fetch-1} for '{keyword}'")
                results = service.cse().list(
                    q=keyword,
                    cx=self.google_cse_id,
                    num=num_to_fetch,
                    start=start_index
                ).execute()

                if 'items' in results:
                    for item in results.get('items', []):
                        # Basic validation of URL
                        link = item.get('link')
                        if link and isinstance(link, str) and link.startswith('http'):
                             urls.append({
                                 'url': link,
                                 'title': item.get('title'),
                                 'snippet': item.get('snippet', '')
                             })
                        else:
                             logging.warning(f"Skipping invalid URL from search results: {link}")
                else:
                     logging.warning(f"No 'items' found in Google Search results page {i+1} for '{keyword}'.")

                if num_requests > 1:
                    time.sleep(0.5) # Be polite to the API

            logging.info(f"Found {len(urls)} top URLs for '{keyword}'.")
            return urls

        except Exception as e:
            logging.error(f"Error getting Google search results for '{keyword}': {str(e)}", exc_info=True)
            return []

    # --- REVISED (No Scraping) analyze_competitor_content ---
    def analyze_competitor_content(self, keyword, num_results=10, min_successful_scrapes=2):
        """
        Gets URLs only (no scraping) and prepares for AI fallbacks in workflow service.
        Returns analysis dictionary with URLs but relies on AI fallbacks for structure, etc.
        """
        if not keyword:
            log.error("Keyword required")
            return {'error': 'Keyword required'}

        log.info(f"Analyzing competitors for '{keyword}' (URLs only - NO scraping)")

        urls = self.get_top_ranking_urls(keyword, num_results=num_results)
        if not urls:
            log.warning(f"No URLs for '{keyword}'")
            return {'error': 'No competitor URLs found'}

        # Return analysis results with URLs only
        analysis_result = {
            'keyword': keyword,
            'avg_word_count': 0,  # To be calculated in WorkflowService via AI
            'recommended_length': 0,  # To be calculated in WorkflowService via AI
            'content_structure': [],  # To be provided by AI fallback
            'faq_questions': [],  # To be provided by AI fallback
            'example_urls': [url['url'] for url in urls[:5]],  # Keep example URLs
            'successful_scrape_count': 0,  # Always 0 since we don't scrape
            'error': None  # No error if processing finishes
        }

        log.info(f"Completed no-scrape competitor analysis for '{keyword}'. Returning URLs only.")
        return analysis_result
    # --- END REVISED analyze_competitor_content ---

    # --- SIMPLIFIED analyze_content_gaps ---
    def analyze_content_gaps(self, query: str, competitor_analysis: dict) -> dict:
        """
        Checks only for existing blog posts (optional) or returns default.
        Category checking is moved to ContentWorkflowService.
        """
        log.debug(f"Analyzing content gaps for query: '{query}' (Blog Post Check Only)")

        has_blog_post = False
        recommendation = 'create_new' # Default recommendation
        reason = 'Defaulting to create_new. Category check happens in workflow.'

        if not self.wp_service:
            log.warning("WordPressService not available, cannot check for existing posts.")
        else:
            try:
                # Optional: Check for existing Blog Post
                post_rest_base = 'posts'
                if self.wp_service.check_content_exists(query, rest_base=post_rest_base):
                    log.info(f"Found potentially matching blog post for '{query}'.")
                    has_blog_post = True
                    # Keep recommendation as 'create_new' for now, just note existence
                    reason = 'Potentially related blog post found. Review before creating new.'

            except Exception as e:
                log.error(f"Error checking for existing blog post for '{query}': {e}")
                reason = f'Error during blog post check: {str(e)}'

        # Return default state - category check/recommendation happens later
        return {
            'recommendation': recommendation,
            'has_blog_content': has_blog_post,
            'has_product_category': False, # Will be determined later
            'reason': reason,
            'update_targets': [], # Will be populated later if needed
            'category_word_limit': 500
        }
    # --- END SIMPLIFIED analyze_content_gaps ---

    def parse_content_structure(self, headings):
        """Parse structure from a single list of headings."""
        structure = []
        if not headings: return structure
        for heading in headings:
            if not isinstance(heading, str): continue # Skip non-strings
            # More aggressive cleaning for structure parsing
            clean_heading = re.sub(r'[^\w\s]', '', heading).strip() # Remove all non-alphanumeric/space
            clean_heading = re.sub(r'\s+', ' ', clean_heading) # Normalize whitespace
            if 3 < len(clean_heading) < 100:
                 structure.append(clean_heading.title()) # Title case for consistency
        return structure

    def derive_content_structure(self, competitor_headings_list):
        """Derive common structure from multiple lists of competitor headings."""
        if not competitor_headings_list: return []
        # Flatten and parse structure for each competitor first
        parsed_structures = [self.parse_content_structure(h_list) for h_list in competitor_headings_list]
        # Flatten all parsed headings
        all_parsed_headings = [h for structure in parsed_structures for h in structure]
        if not all_parsed_headings: return []

        heading_counter = Counter(all_parsed_headings)
        # Require heading to appear in > 20% of competitors (min 2)
        min_occurrence = max(2, math.ceil(len(competitor_headings_list) * 0.2))
        common_headings = [h for h, c in heading_counter.most_common(50) if c >= min_occurrence]

        if not common_headings: # Fallback if no headings meet threshold
            common_headings = [h for h, c in heading_counter.most_common(10)] # Just top 10 most frequent

        # Try to maintain relative order based on first appearance
        ordered_structure = sorted(common_headings, key=lambda h: min(all_parsed_headings.index(head) for head in all_parsed_headings if head == h))

        # Refine structure: Ensure Intro/Conclusion, remove duplicates (case-insensitive)
        final_structure = []
        seen_lower = set()

        # Add Intro if missing
        if not any(s.lower().startswith('intro') for s in ordered_structure):
             final_structure.append("Introduction")
             seen_lower.add("introduction")

        # Add common headings, skipping duplicates and typical end sections
        end_section_hints = {'conclu', 'summary', 'faq', 'final thought', 'wrap up'}
        for heading in ordered_structure:
             heading_lower = heading.lower()
             if heading_lower not in seen_lower and not any(hint in heading_lower for hint in end_section_hints):
                  final_structure.append(heading)
                  seen_lower.add(heading_lower)

        # Add FAQ if missing and space allows
        if not any('faq' in s or 'question' in s for s in seen_lower) and len(final_structure) < 10:
             final_structure.append("Frequently Asked Questions")
             seen_lower.add("frequently asked questions")

        # Add Conclusion if missing
        if not any(hint in s for hint in end_section_hints for s in seen_lower):
             final_structure.append("Conclusion")

        return final_structure[:12] # Limit final section count

    def extract_questions_from_content(self, content_snippets: List[str]) -> List[str]:
        questions = set()
        question_pattern = re.compile(r'(?:^|\.\s+|\n\s*)([A-Z][^.?!]*\?)')
        question_starters = ('what', 'how', 'why', 'when', 'where', 'which', 'who', 'can', 'do', 'is', 'are', 'should', 'does', 'will', 'could', 'would')

        for snippet in content_snippets:
             if not isinstance(snippet, str): continue
             # Snippet is already plain text from scraping
             matches = question_pattern.findall(snippet)
             for match in matches:
                 question = match.strip()
                 if 15 < len(question) < 250 \
                    and question.count(' ') >= 2 \
                    and question.lower().startswith(question_starters) \
                    and '...' not in question:
                     questions.add(question)
        log.info(f"Extracted {len(questions)} potential FAQs.")
        return sorted(list(questions))[:10] # Limit FAQs returned