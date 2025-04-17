import os
import logging
import time
import json
import re
from datetime import datetime
import anthropic
import random
from typing import Optional, List, Dict
import pandas as pd
import numpy as np
import requests
from collections import Counter
from urllib.parse import urlparse
import difflib # <-- Import difflib for fuzzy matching
import html
from io import BytesIO


# Assuming other services are imported
from .content_analyzer import ContentAnalyzer
from .imagen import ImagenClient
from .wordpress import WordPressService


# --- Helper function safe_get ---
def safe_get(data, key, default=None):
    """Safely get value from either Series or dict"""
    if isinstance(data, pd.Series):
        val = data.get(key, default)
        if pd.isna(val): return default
        if isinstance(val, np.generic): return val.item()
        return val
    elif isinstance(data, dict):
        return data.get(key, default)
    return default
# --- End Helper ---

log = logging.getLogger(__name__)

class ContentWorkflowService:
    """Handles the content generation and posting workflow steps."""

    def __init__(self, anthropic_api_key, anthropic_model, anthropic_max_tokens, anthropic_rate_limit, anthropic_max_retries,
                 content_analyzer: ContentAnalyzer,
                 imagen_client: ImagenClient,
                 wordpress_service: WordPressService):
        self.analyzer = content_analyzer
        self.imagen_client = imagen_client
        self.wp_service = wordpress_service
        self.anthropic_api_key = anthropic_api_key
        self.claude_model = anthropic_model
        self.claude_max_tokens = anthropic_max_tokens
        self.rate_limit_per_minute = anthropic_rate_limit
        self.max_retries = anthropic_max_retries
        self.last_request_time = 0
        self.anthropic_client = None
        if self.anthropic_api_key:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                log.info(f"Anthropic client initialized for model: {self.claude_model}")
            except Exception as e:
                log.error(f"Failed to initialize Anthropic client: {e}")
        else:
            log.warning("Anthropic API key was not provided.")

        self.ke_api_key = self.analyzer.ke_api_key
        if not self.ke_api_key:
            log.warning("KE API Key not found in analyzer config. KE calls disabled.")

    def _build_image_prompt(self, keyword: str, snippet: str | None = None) -> str:
        """
        Build a one‑liner prompt for Imagen:
        - 16:9 photorealistic
        - modern man‑cave for sports enthusiasts (35–45 y/o)
        - sleek lines, contemporary finishes
        - pool table, sports memorabilia (framed jerseys, neon signs)
        - warm dynamic + subtle LED accent lighting
        - realistic textures
        - no text overlays or watermarks
        """
        base = (
            f"Create a photorealistic 16:9 image showcasing {keyword} "
            "in a modern man‑cave designed for sports enthusiasts aged 35 to 45, "
            "with sleek lines, contemporary finishes, a pool table, and sports memorabilia "
            "(framed jerseys, neon signs). Use warm dynamic lighting with subtle LED accents "
            "and realistic textures. No text overlays or watermarks."
        )
        if snippet:
            base += " " + snippet.strip()
        return base

    def _apply_rate_limiting(self):
        """Apply rate limiting for Claude API calls."""
        if not self.anthropic_client: return
        try:
             min_interval = 60.0 / self.rate_limit_per_minute
             # Handle potential division by zero if rate limit is 0
             if min_interval <= 0: min_interval = 1.0 # Default minimum interval
        except ZeroDivisionError:
             min_interval = 1.0

        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < min_interval:
            wait_time = min_interval - time_since_last
            log.info(f"Rate limiting: waiting {wait_time:.2f} seconds")
            time.sleep(wait_time)
        self.last_request_time = time.time()

    # --- MODIFIED _make_ke_request ---
    def _make_ke_request(self, endpoint_url: str, payload: dict) -> Optional[dict]: # Return full dict
        """Helper function to make Keywords Everywhere API calls."""
        if not self.ke_api_key:
            log.error(f"Cannot call KE endpoint {endpoint_url}, API key missing.")
            return None

        log.info(f"Calling KE API: {endpoint_url} with payload keys: {list(payload.keys())}") # Log keys only
        log.debug(f"Full KE Payload: {payload}") # Debug full payload
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.ke_api_key}'
            # KE uses form data, requests handles Content-Type
        }
        time.sleep(0.7) # Slightly increased delay for KE politeness

        try:
            response = requests.post(endpoint_url, data=payload, headers=headers, timeout=45) # Increased timeout

            if response.status_code == 200:
                response_data = response.json()
                credits = response_data.get('credits_consumed', 0)
                log.info(f"KE API success for {payload.get('keyword') or payload.get('url')}. Credits used: {credits}")
                return response_data # Return the full parsed JSON response
            elif response.status_code == 402:
                 error_data = response.json()
                 log.error(f"KE API Error (402) for {payload.get('keyword') or payload.get('url')}: {error_data.get('message')} - {error_data.get('description')}")
                 return None
            else:
                log.error(f"KE API Error for {payload.get('keyword') or payload.get('url')}: Status {response.status_code} - Response: {response.text[:300]}")
                return None

        except requests.exceptions.Timeout:
             log.error(f"KE API request timed out for {payload.get('keyword') or payload.get('url')}")
             return None
        except requests.exceptions.RequestException as e:
            log.error(f"KE API request failed for {payload.get('keyword') or payload.get('url')}: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error during KE API call for {payload.get('keyword') or payload.get('url')}: {e}", exc_info=True)
            return None
    # --- END MODIFIED _make_ke_request ---

    # --- MODIFIED _get_ke_pasf ---
    def _get_ke_pasf(self, keyword: str, num: int = 10) -> List[str]:
        """Gets 'People Also Search For' keywords from KE API."""
        endpoint = "https://api.keywordseverywhere.com/v1/get_pasf_keywords"
        payload = {"keyword": keyword, "num": num}
        response_data = self._make_ke_request(endpoint, payload)
        # Data format is array of strings
        return response_data.get('data', []) if response_data and isinstance(response_data.get('data'), list) else []
    # --- END MODIFIED _get_ke_pasf ---

    # --- MODIFIED _get_ke_related ---
    def _get_ke_related(self, keyword: str, num: int = 15) -> List[str]:
        """Gets 'Related Keywords' from KE API."""
        endpoint = "https://api.keywordseverywhere.com/v1/get_related_keywords"
        payload = {"keyword": keyword, "num": num}
        response_data = self._make_ke_request(endpoint, payload)
        # Data format is array of strings
        return response_data.get('data', []) if response_data and isinstance(response_data.get('data'), list) else []
    # --- END MODIFIED _get_ke_related ---

    # --- NEW: KE URL Keywords Helper ---
    def _get_ke_url_keywords(self, url: str, country: str = "us", num: int = 50) -> List[str]:
        """Gets keywords a specific URL ranks for from KE API."""
        endpoint = "https://api.keywordseverywhere.com/v1/get_url_keywords"
        payload = {"url": url, "country": country, "num": num}
        response_data = self._make_ke_request(endpoint, payload)
        if response_data and isinstance(response_data.get('data'), list):
             # Extract just the keyword strings from the list of objects
             keywords = [item.get('keyword') for item in response_data['data'] if isinstance(item, dict) and item.get('keyword')]
             log.info(f"Extracted {len(keywords)} keywords for URL: {url}")
             return keywords
        log.warning(f"Could not extract keywords for URL {url}. Response data: {response_data}")
        return []
    # --- END NEW KE URL Keywords Helper ---

    # --- AI Fallback Methods ---
    def _get_ai_suggestion(self, prompt: str, system_prompt: str, max_tokens: int = 500) -> Optional[str]:
        """Helper to get suggestions from Claude with retries."""
        if not self.anthropic_client:
            log.error("Anthropic client not available for AI suggestions.")
            return None

        retries = 0
        while retries < self.max_retries:
            self._apply_rate_limiting()
            try:
                message = self.anthropic_client.messages.create(
                    model=self.claude_model,
                    max_tokens=max_tokens,
                    temperature=0.5, # Slightly creative for suggestions
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                response_text = message.content[0].text.strip()
                log.debug(f"AI Suggestion Raw Response: {response_text[:200]}...")
                return response_text
            except anthropic.APIConnectionError as e:
                log.warning(f"Anthropic connection error (Attempt {retries+1}): {e}")
            except anthropic.RateLimitError as e:
                log.warning(f"Anthropic rate limit error (Attempt {retries+1}): {e}")
                time.sleep((2 ** retries) * 5 + random.uniform(0, 3)) # Longer backoff for rate limits
            except anthropic.APIStatusError as e:
                log.error(f"Anthropic API status error ({e.status_code}) (Attempt {retries+1}): {e.response}")
                if e.status_code < 500: break # Don't retry client errors
            except Exception as e:
                log.error(f"Unexpected error getting AI suggestion (Attempt {retries+1}): {e}", exc_info=True)

            retries += 1
            if retries < self.max_retries:
                wait_time = (2 ** (retries - 1)) + random.uniform(0, 1)
                log.info(f"Waiting {wait_time:.2f}s before retry...")
                time.sleep(wait_time)

        log.error("Failed to get AI suggestion after multiple retries.")
        return None

    def _get_ai_keywords(self, keyword: str) -> dict:
        log.info(f"Using AI fallback to generate keywords for '{keyword}'")
        prompt = f"""Suggest relevant keywords for a blog post about "{keyword}". Provide:
1.  Up to 10 primary keywords (most important, high relevance).
2.  Up to 15 secondary keywords (related terms, variations).

Format the response ONLY as a JSON object like this:
{{
  "primary": ["keyword1", "keyword2", ...],
  "secondary": ["keyword3", "keyword4", ...]
}}"""
        system_prompt="You are an SEO keyword research assistant."
        response = self._get_ai_suggestion(prompt, system_prompt)
        if response:
            try:
                # Try to find JSON within potentially messy response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    return {
                        'must_have': data.get('primary', []),
                        'recommended': data.get('secondary', [])
                    }
                else:
                     log.warning("Could not extract JSON from AI keyword response.")
            except json.JSONDecodeError:
                log.warning(f"Failed to parse AI keyword suggestions as JSON: {response}")
        return {'must_have': [keyword], 'recommended': []} # Fallback includes main keyword

    def _get_ai_structure(self, keyword: str) -> list:
        log.info(f"Using AI fallback to generate structure for '{keyword}'")
        prompt = f"""Suggest a logical article structure (section headings) for a comprehensive blog post about "{keyword}". Provide 7-9 headings excluding introduction and conclusion.

Format the response ONLY as a simple JSON list of strings:
["Heading 1", "Heading 2", ...]"""
        system_prompt="You are an expert content outline creator."
        response = self._get_ai_suggestion(prompt, system_prompt)
        structure = ["Introduction", f"Understanding {keyword.title()}", "Key Features", "Benefits", "Conclusion"] # Basic default
        if response:
            try:
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    headings = json.loads(json_match.group(0))
                    if isinstance(headings, list) and len(headings) > 2:
                        structure = ["Introduction"] + headings + ["Conclusion"]
                else:
                    log.warning("Could not extract JSON list from AI structure response.")
            except json.JSONDecodeError:
                 log.warning(f"Failed to parse AI structure suggestions as JSON: {response}")
        return structure

    def _get_ai_faqs(self, keyword: str) -> list:
        log.info(f"Using AI fallback to generate FAQs for '{keyword}'")
        prompt = f"""Suggest 3-5 frequently asked questions (FAQs) a user searching for "{keyword}" might have.

Format the response ONLY as a simple JSON list of strings:
["Question 1?", "Question 2?", ...]"""
        system_prompt="You generate relevant FAQ questions based on a keyword."
        response = self._get_ai_suggestion(prompt, system_prompt)
        faqs = []
        if response:
            try:
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    faqs = json.loads(json_match.group(0))
                    if not isinstance(faqs, list): faqs = [] # Ensure it's a list
                else:
                    log.warning("Could not extract JSON list from AI FAQ response.")
            except json.JSONDecodeError:
                 log.warning(f"Failed to parse AI FAQ suggestions as JSON: {response}")
        return faqs[:5] # Return up to 5

    def _get_ai_word_count(self, keyword: str) -> int:
        log.info(f"Using AI fallback to estimate word count for '{keyword}'")
        prompt = f"""Based on the keyword "{keyword}", estimate an appropriate target word count for a comprehensive, high-quality blog post. Consider typical user intent and topic depth.

Respond ONLY with the integer number (e.g., 1500, 2000, 2500, 3000)."""
        system_prompt="You estimate appropriate article lengths based on keywords."
        response = self._get_ai_suggestion(prompt, system_prompt, max_tokens=50)
        word_count = 1500 # Default fallback
        if response:
            match = re.search(r'\b(\d{3,4})\b', response) # Look for 3 or 4 digit number
            if match:
                try:
                    word_count = int(match.group(1))
                    # Basic sanity check
                    word_count = min(max(1000, word_count), 5000)
                except ValueError:
                     log.warning(f"Could not parse word count number from AI response: {response}")
            else:
                 log.warning(f"Could not find word count number in AI response: {response}")

        log.info(f"AI estimated word count: {word_count}")
        return word_count

    # --- MODIFIED generate_content_brief ---
    # Fix for ContentWorkflowService class - use the exact method name expected

    def generate_content_brief(self, query_data):
        """
        Generates a content brief using KE APIs, Google Search for URLs (no scraping),
        AI fallbacks for structure/FAQs/WC, and checks for existing categories.

        The method now accepts cached category data via query_data to avoid repeatedly
        fetching the same categories from WordPress.
        """
        query = safe_get(query_data, 'query', 'Unknown Query')
        if query == 'Unknown Query': log.error(f"Invalid query data: {query_data}"); return None
        log.info(f"Generating brief for query: '{query}'")

        # --- Data Gathering ---
        must_include_phrases = []
        recommended_phrases = []
        pasf_keywords = []
        related_keywords = []
        content_structure = []
        faq_questions = []
        example_urls = []
        recommended_length = 1500 # Default
        avg_word_count = 0
        analysis_failed = False
        analysis_error_msg = None
        notes_addition = ""
        has_product_category = False # Initialize category flag

        try:
            # --- **** START STEP 0: Use cached categories if available **** ---
            product_categories = safe_get(query_data, '_cached_categories', None)
            category_mapping = safe_get(query_data, '_cached_category_mapping', None)

            if product_categories is None:
                # Fall back to fetching categories if not provided in query_data
                log.info(f"No cached categories found. Fetching product categories for '{query}' gap analysis...")
                product_categories = self._fetch_site_categories(taxonomy='product_cat')
                category_names_lower = {cat.get('name','').lower().strip(): cat for cat in product_categories if cat.get('name')}
                log.debug(f"Fetched {len(product_categories)} product categories.")
            else:
                log.info(f"Using cached categories ({len(product_categories)}) for '{query}' gap analysis.")
                if category_mapping is None:
                    # Create mapping only if not provided
                    category_names_lower = {cat.get('name','').lower().strip(): cat for cat in product_categories if cat.get('name')}
                else:
                    # Use provided mapping directly
                    category_names_lower = category_mapping
                    log.debug(f"Using cached category mapping with {len(category_names_lower)} entries.")
            # --- **** END STEP 0 **** ---

            # --- **** STEP 1: Determine Recommendation based on Category Check **** ---
            recommendation = 'create_new'
            reason = 'No matching product category found.'
            update_targets = []
            category_word_limit = 500

            query_lower = query.lower()
            if query_lower in category_names_lower:
                log.info(f"Found EXACT matching product category for '{query}'. Setting recommendation to 'dual_content'.")
                has_product_category = True
                recommendation = 'dual_content'
                reason = 'Matching product category exists. Recommend updating description and creating blog post.'
                matched_cat = category_names_lower[query_lower]
                # Get existing description length (requires enhancement in _fetch_site_categories or separate call)
                # For now, assume length is 0 or fetch separately if needed
                existing_desc_len = 0 # Placeholder
                update_targets.append({
                    'id': matched_cat.get('id'),
                    'title': matched_cat.get('name'), # Use original case name
                    'content_type': 'category',
                    'content_length': existing_desc_len
                })
            # --- **** END STEP 1 **** ---

            # 2. Get competitor URLs from Google Search API (no scraping)
            competitor_analysis = self.analyzer.analyze_competitor_content(query, num_results=15)

            if not competitor_analysis or competitor_analysis.get('error'):
                log.warning(f"Google search API failed for '{query}': {competitor_analysis.get('error', 'Unknown')}. Using AI fallbacks.")
                analysis_failed = True
                analysis_error_msg = competitor_analysis.get('error', 'Search API failed')
                notes_addition = f"[System Note: Google Search API Failed - {analysis_error_msg}. Using AI Fallbacks.]"
                example_urls = []
            else:
                # Extract URLs from successful API search
                example_urls = competitor_analysis.get('example_urls', [])
                log.info(f"Received {len(example_urls)} top URLs for '{query}' from Google Search API.")

            # 3. Use AI fallbacks for structure, FAQs, and word count
            log.info(f"Using AI fallbacks for content structure, FAQs, and word count for '{query}'")
            content_structure = self._get_ai_structure(query)
            faq_questions = self._get_ai_faqs(query)
            recommended_length = self._get_ai_word_count(query)

            # 4. Get Keywords using KE APIs (URL Keywords, PASF, Related)
            all_competitor_keywords = []
            if example_urls:
                log.info(f"Fetching KE URL Keywords for {len(example_urls)} competitor URLs...")
                for url in example_urls:
                    keywords_for_url = self._get_ke_url_keywords(url, num=50)
                    if keywords_for_url: # Check if list is not empty
                        all_competitor_keywords.extend(keywords_for_url)
                    time.sleep(0.2)

                if all_competitor_keywords:
                    keyword_counts = Counter(all_competitor_keywords)
                    must_include_phrases = [kw for kw, count in keyword_counts.most_common(100) if count >= 2][:15]
                    needed = 15 - len(must_include_phrases)
                    if needed > 0: must_include_phrases.extend([kw for kw, count in keyword_counts.most_common(15) if kw not in must_include_phrases][:needed])
                    recommended_phrases = [kw for kw, count in keyword_counts.most_common(100) if kw not in must_include_phrases][:30]
                    log.info(f"Generated {len(must_include_phrases)} must-include and {len(recommended_phrases)} recommended keywords from KE URL data.")
                else: log.warning(f"KE URL Keywords API returned no keywords for competitors of '{query}'.")
            else: log.warning(f"No competitor URLs available to fetch KE keywords for '{query}'.")

            # Fallback/Supplement keywords if KE failed/returned little
            if not must_include_phrases:
                log.warning(f"No keywords from KE for '{query}'. Using AI keyword fallback.")
                ai_keywords = self._get_ai_keywords(query)
                must_include_phrases = ai_keywords.get('must_have', [query])
                recommended_phrases = ai_keywords.get('recommended', [])

            pasf_keywords = self._get_ke_pasf(query, num=10)
            related_keywords = self._get_ke_related(query, num=15)
            # ---

            # 5. Assemble the Brief Dictionary
            try:
                cpc_data = safe_get(query_data, 'cpc', {'value': '0.00'})
                cpc_value = float(safe_get(cpc_data, 'value', '0.00') if isinstance(cpc_data, dict) else cpc_data or '0.00')
            except: pass # Ignore errors parsing CPC

            opp_score_val = float(safe_get(query_data, 'opportunity_score', 0.0))
            priority_level = '1' if opp_score_val > 60 else \
                            '2' if opp_score_val > 45 else \
                            '3' if opp_score_val > 25 else \
                            '4'

            brief = {
                # Basic info & GSC Metrics
                'keyword': query,
                'search_intent': safe_get(query_data, 'intent', self.analyzer.classify_query_intent(query)),
                'current_position': round(float(safe_get(query_data, 'avg_position', 100.0)), 2),
                'monthly_searches': int(safe_get(query_data, 'monthly_search_volume', 0)),
                'opportunity_score': opp_score_val, # Original score
                'cpc': f"${cpc_value:.2f}",
                'competition': float(safe_get(query_data, 'competition', 0.5)),
                'total_impressions': int(safe_get(query_data, 'total_impressions', 0)),
                'total_clicks': int(safe_get(query_data, 'total_clicks', 0)),
                'avg_ctr': float(safe_get(query_data, 'avg_ctr', 0.0)),

                # Content Details
                'target_word_count': recommended_length,
                'must_include_phrases': must_include_phrases,
                'recommended_phrases': recommended_phrases,
                'content_structure': content_structure,
                'faq_questions': faq_questions,
                'pasf_keywords': pasf_keywords,
                'related_keywords': related_keywords,
                'example_urls': example_urls,
                'avg_word_count': avg_word_count,

                # Content gap / Action data
                'content_recommendation': recommendation, # Use the determined value
                'content_exists': has_product_category, # Primarily based on category check now
                'update_targets': update_targets, # Use populated list if category matched
                'update_targets_text': "\n".join([f"- {t.get('title', 'N/A')} ..." for t in update_targets]),
                'category_word_limit': category_word_limit, # Needed for prompt

                # Meta / Workflow
                'priority_level': priority_level,
                'notes': notes_addition.strip() + (f" | Reason: {reason}" if reason else ""), # Add reason to notes
                'generated_date': datetime.now().strftime('%Y-%m-%d')
            }

            # 6. Generate Final Claude Prompt
            brief['claude_prompt'] = self._generate_claude_prompt(brief)

            if not brief['claude_prompt']:
                log.error(f"Failed to generate Claude prompt for '{query}'.")
                return None

            log.info(f"Successfully generated brief dictionary for: '{query}' (Analysis Failed: {analysis_failed})")
            return brief

        except Exception as e:
            query_label = safe_get(query_data, 'query', 'unknown query')
            log.error(f"Error generating brief for '{query_label}': {str(e)}", exc_info=True)
            return None

    # --- MODIFIED _generate_claude_prompt ---
    def _generate_claude_prompt(self, brief):
        """
        Generates the detailed prompt for Claude, requesting link suggestions
        in the format matching the WPCodeBox snippet.
        """
        log.debug(f"Generating Claude prompt for keyword: {brief.get('keyword', 'N/A')}")
        try:
            # --- Extract data from brief ---
            keyword = brief.get('keyword', 'this topic')
            target_word_count = brief.get('target_word_count', 1500)
            search_intent = brief.get('search_intent', 'informational')
            must_include = brief.get('must_include_phrases', [])
            recommended = brief.get('recommended_phrases', [])
            structure = brief.get('content_structure', [])
            faqs = brief.get('faq_questions', [])
            pasf = brief.get('pasf_keywords', [])
            related = brief.get('related_keywords', [])
            recommendation_type = brief.get('content_recommendation', 'create_new')
            update_targets = brief.get('update_targets', [])
            category_word_limit = brief.get('category_word_limit', 500)

            # --- Keyword Formatting ---
            primary_kw_str = "\n".join(f"- {kw}" for kw in must_include[:15]) if must_include else f"- {keyword}"
            secondary_kw_str = "\n".join(f"- {kw}" for kw in recommended[:30]) if recommended else "N/A"
            # ---

            # --- PASF / Related Formatting ---
            pasf_str = "\n".join(f"- {kw}" for kw in pasf) if pasf else "N/A"
            related_str = "\n".join(f"- {kw}" for kw in related) if related else "N/A"
            # ---

            # --- Structure Formatting ---
            if not structure or len(structure) < 3: structure = ["Introduction", f"Exploring {keyword.title()}", "Key Considerations", "Conclusion"]
            structure_str = "\n".join(f"{i+1}. {section}" for i, section in enumerate(structure))
            # ---

            # --- FAQ Formatting ---
            faq_str = ""
            if faqs:
                faq_str = "Frequently Asked Questions to Address:\n" + "\n".join(f"- {q}" for q in faqs[:10])
            else:
                faq_str = "Frequently Asked Questions to Address:\n" + f"- What is {keyword}?\n" + f"- Why is {keyword} important?\n" + f"- How do I choose the right {keyword if ' ' in keyword else 'item'}?"
            # ---

            # --- Content Specs ---
            content_specs_list = [
                f"- Primary Keyword Focus: **{keyword}**",
                f"- Search Intent: {search_intent}",
                f"- Target Word Count: **EXACTLY {target_word_count} words** (Strict Requirement)"
            ]
            dual_content_instructions = ""
            if recommendation_type == 'dual_content':
                content_specs_list.append(f"- Target word count for category description: 350-{category_word_limit} words")
                content_specs_list.append(f"- Target word count for blog post: {target_word_count} words")
                if update_targets:
                    content_specs_list.append(f"- Update the following category description and create a related blog post:")
                    for target in update_targets:
                        title = safe_get(target, 'title', 'Untitled')
                        length = safe_get(target, 'content_length', 0)
                        content_specs_list.append(f"  * {title} (Current length: {length} words)")
                    content_specs_list.append(f"- The category description should be concise (350-{category_word_limit} words) and focused on helping shoppers")
                    content_specs_list.append(f"- The blog post should be comprehensive ({target_word_count} words) and educational")
                    content_specs_list.append(f"- Include cross-linking between the category and blog post")

                # Make sure .format() has all needed variables
                dual_content_instructions = """
    Special Formatting Instructions for Dual Content:
    Please format your response with clear separation between the two content pieces:

    === CATEGORY DESCRIPTION ===
    [Category description content here - 350-{category_word_limit} words]

    === BLOG POST ===
    [Full blog post content here - target word count as specified ({target_word_count} words)]

    For the category description:
    - Focus on helping shoppers make purchase decisions
    - Mention key benefits and features of our products
    - Include a brief "Learn more about [{keyword}] in our detailed guide: [BLOG TITLE]" at the end (replace bracketed terms)

    For the blog post:
    - Create comprehensive, educational content
    - Include a "Shop our collection of [{keyword}] at Cave Supplies" with a reference to the category (replace bracketed term)
    - Focus on answering common questions and providing value
    """.format(keyword=keyword, category_word_limit=category_word_limit, target_word_count=target_word_count)

            content_specs = "\n".join(content_specs_list)
            # ---

            # --- Brand Context ---
            # Fill in the full text here
            brand_context = """
    Brand Voice and Context:
    - Website: Cave Supplies - online retailer of man cave furniture and home decor (bars, game rooms, home theaters, offices).
    - Target Audience: Men personalizing smaller spaces, or those whose partners manage main home decor. Focus on versatility and space-efficiency.
    - Mascot (Optional): Thorak, a prehistoric caveman amazed by modern comforts (use sparingly for humor, simple broken sentences: "Thorak like sturdy stool.").
    - Tone: Authoritative but approachable and relatable for the target audience. We sell premium products, so avoid overly casual or slang language. Focus on quality, features, benefits, and helping the user create their ideal space.
    """
            # ---

            # --- Keyword Usage Instructions ---
            keyword_usage_instructions = f"""
    Keyword Usage Instructions & Internal Linking:
    - **Strict Relevance Required:** Your primary goal is to create the best possible article about **"{keyword}"**.
    - **Evaluate Provided Keywords:** Below are keyword lists derived from competitor analysis (what they rank for), user searches (PASF), and related topics. YOU MUST EVALUATE these lists critically.
    - **INCLUDE ONLY TOPICALLY RELEVANT KEYWORDS** that directly relate to **"{keyword}"** and fit naturally within the article's context.
    - **EXCLUDE / IGNORE:**
        - **Competitor Brand Names:** Absolutely do not mention competitor brands like Wayfair, Amazon, Etsy, Overstock, IKEA, Target, Walmart, Home Depot, Lowes, etc..
        - **Generic/Navigational Terms:** Ignore terms like 'login', 'near me', 'store', 'customer service', 'free shipping', 'sale', 'discount', 'clearance', 'coupon', 'location', 'reviews' .
        - **Clearly Unrelated Topics:** Disregard keywords about unrelated product categories (e.g., if the topic is 'bar stools', ignore 'dog ramps', 'rugs', 'carpets', 'outdoor pools', 'kitchen appliances', 'sweater dressers', 'bedding', 'sofas' unless it's a 'sofa bed'). Use common sense to determine relevance to the main topic: **"{keyword}"**. If a term seems borderline, err on the side of *not* including it if it distracts from the main topic.
        - **Poor Quality/Gibberish:** Ignore any keywords that look like errors, code snippets, or are nonsensical.
    - **Natural Integration:** Weave the *relevant* selected keywords naturally into the text. Avoid forcing keywords or creating unnatural sentences (keyword stuffing). Prioritize using the Primary list keywords most often.
        - **Internal Link Suggestions:** As you write, identify 8-12 opportunities for internal links (product categories, related products, specific features). Format these suggestions EXACTLY as follows, replacing the placeholder text:
        `<span class="link-opportunity" data-link-suggestion="Describe the ideal target page here">exact phrase to link</span>`
    - **Example Link Suggestions:**
        - `...check out our collection of <span class="link-opportunity" data-link-suggestion="Product category page for wooden bar stools">wooden bar stools</span> for a classic look.`
        - `...consider <span class="link-opportunity" data-link-suggestion="Product category page for swivel bar stools">swivel functionality</span> if you need flexibility.`
    """
            # ---

            # --- Content & Formatting Guidelines ---
            content_guidelines = f"""
    Content & Formatting Guidelines:
    - Write comprehensive, valuable, and engaging content focused on **"{keyword}"**. Ensure factual accuracy.
    - Use proper HTML: <h2> for main sections (aim for 8-10+ sections to achieve the target word count), <h3> for subsections, <p> for paragraphs, <ul>/<li> for lists, <strong>/<em> for emphasis where appropriate.
    - DO NOT include an H1 title tag. Start content directly with the first `<h2>` tag.
    - Structure content logically using the suggested outline below as a guide, but feel free to adapt it if necessary for quality and flow.
    - Use short paragraphs (generally 2-4 sentences) and bullet points for better readability.
    - Include a compelling Introduction that hooks the reader and a strong Conclusion that summarizes key takeaways.
    - Address relevant FAQs from the list below, ideally in a dedicated FAQ section near the end using H3 for each question.
    - Maintain the Cave Supplies brand voice (authoritative, knowledgeable, helpful, slightly informal but professional, aimed at men building their personal space).
    - Mention "Cave Supplies" only minimally (1-2 times max), perhaps in the conclusion as a call to action (e.g., "Explore the collection at Cave Supplies").
    - **Word Count:** The final output MUST be **EXACTLY {target_word_count} words**. Count your words carefully before finishing. If you are under the word count, expand on existing points with more detail, examples, or explanations rather than adding filler.
    """
            # ---

            # --- Final Prompt Assembly ---
            prompt = f"""Please write a comprehensive, SEO-optimized blog article about **"{keyword}"**.

    --- Core Article Requirements ---
    {content_specs}

    {brand_context}

    {keyword_usage_instructions}

    --- Provided Keyword Data (Evaluate for Relevance) ---
    Keywords Competitors Rank For (Primary - Use RELEVANT ones most):
    {primary_kw_str}

    Keywords Competitors Rank For (Secondary - Use RELEVANT ones):
    {secondary_kw_str}

    People Also Search For (Address RELEVANT user interests):
    {pasf_str}

    Related Keywords (Incorporate RELEVANT ones):
    {related_str}

    --- Content Structure & Questions ---
    Suggested Article Structure:
    {structure_str}

    Frequently Asked Questions to Address (if relevant):
    {faq_str}

    {dual_content_instructions}

    {content_guidelines}

    Begin the article directly with the first `<h2>` tag.
    """
            # Clean up potential leading/trailing whitespace from multiline strings and extra newlines
            prompt_lines = [line.strip() for line in prompt.splitlines() if line.strip()]
            final_prompt = "\n".join(prompt_lines)

            log.debug(f"Generated Claude prompt length: {len(final_prompt)} for keyword '{keyword}'")
            if len(final_prompt) < 500: log.warning(f"Generated prompt for '{keyword}' seems unusually short.")

            return final_prompt

        except Exception as e:
            log.error(f"Error generating Claude prompt for brief '{brief.get('keyword', 'N/A')}': {e}", exc_info=True)
            return "" # Return empty string on error

    # --- **** REVISED _fetch_site_categories (Correct Namespace) **** ---
    def _fetch_site_categories(self, taxonomy='product_cat') -> List[Dict]:
        """Fetches all terms for a given taxonomy using WP REST API."""
        if not self.wp_service:
            log.error("WordPressService not available to fetch categories.")
            return []

        # --- Determine the correct NAMESPACED REST base ---
        namespaced_rest_base = None
        if taxonomy == 'product_cat':
             # Use the standard WooCommerce REST base and namespace
             namespaced_rest_base = 'wc/v3/products/categories'
             log.info(f"Using namespaced REST base '{namespaced_rest_base}' for taxonomy '{taxonomy}'.")
        elif taxonomy == 'category':
             namespaced_rest_base = 'wp/v2/categories' # Standard WP category
             log.info(f"Using namespaced REST base '{namespaced_rest_base}' for taxonomy '{taxonomy}'.")
        elif taxonomy == 'post_tag':
             namespaced_rest_base = 'wp/v2/tags' # Standard WP tag
             log.info(f"Using namespaced REST base '{namespaced_rest_base}' for taxonomy '{taxonomy}'.")
        else:
             # For other taxonomies, assume standard WP namespace + taxonomy slug
             # This might need adjustment based on how custom taxonomies are registered
             namespaced_rest_base = f'wp/v2/{taxonomy}'
             log.warning(f"Assuming standard namespaced REST base '{namespaced_rest_base}' for taxonomy '{taxonomy}'. Verify if correct.")
        # --- End REST base determination ---

        if not namespaced_rest_base:
             log.error(f"Could not determine namespaced REST base for taxonomy '{taxonomy}'.")
             return []

        all_terms = []
        seen_ids = set()
        page = 1
        per_page = 100
        MAX_PAGES = 10

        while True:
            if page > MAX_PAGES:
                log.warning(f"Reached maximum page limit ({MAX_PAGES}) fetching taxonomy '{taxonomy}'. Stopping.")
                break

            # Construct endpoint using the determined NAMESPACED REST base
            # The query parameters are appended by _make_request
            endpoint_with_params = f"{namespaced_rest_base}?per_page={per_page}&page={page}&orderby=name&order=asc&_fields=id,name,slug,parent,count"
            log.info(f"Fetching {taxonomy} page {page} using namespaced endpoint: {namespaced_rest_base}")
            log.debug(f"Full endpoint with params for _make_request: {endpoint_with_params}")


            terms_data = None
            try:
                # Pass the namespaced base and let _make_request handle params
                # We need to separate the base from the params for _make_request
                params_for_request = {
                    'per_page': per_page,
                    'page': page,
                    'orderby': 'name',
                    'order': 'asc',
                    '_fields': 'id,name,slug,parent,count'
                }
                terms_data = self.wp_service._make_request('GET', namespaced_rest_base, params=params_for_request)
            except Exception as e:
                log.error(f"Exception during _make_request call from _fetch_site_categories: {e}")
                terms_data = None # Treat exception as failure

            # Check if the request was successful and returned a list
            if terms_data is not None and isinstance(terms_data, list):
                # Process the received terms
                new_terms_on_page = 0
                for term in terms_data:
                    term_id = term.get('id')
                    if term_id and term_id not in seen_ids:
                        seen_ids.add(term_id)
                        all_terms.append(term)
                        new_terms_on_page += 1

                log.info(f"Fetched {len(terms_data)} terms on page {page}, added {new_terms_on_page} new unique terms. Total unique: {len(all_terms)}")

                # Check if this was the last page
                if len(terms_data) < per_page:
                    log.info(f"Last page reached for taxonomy '{taxonomy}'.")
                    break # Exit loop, no more terms

                page += 1 # Go to the next page
                time.sleep(0.1) # Small delay between pages

            else:
                # Handle API error or unexpected response format
                log.error(f"Failed to fetch or parse data for {taxonomy} page {page}. Response from _make_request: {terms_data}. Stopping fetch.")
                break # Exit loop on error

        log.info(f"Finished fetching. Total unique terms found: {len(all_terms)} for taxonomy '{taxonomy}'.")
        return all_terms
    # --- END REVISED ---

    # --- NEW: Fuzzy Match Category ---
    @staticmethod
    def _fuzzy_match_category(anchor_text: str, category_mapping: Dict, threshold=0.75) -> Optional[Dict]:
        """Finds the best fuzzy match for anchor text in category names/slugs."""
        anchor_text_lower = anchor_text.lower().strip()
        if not anchor_text_lower: return None

        best_match_cat = None
        best_ratio = threshold

        for cat_key, cat_data in category_mapping.items():
            # Compare against both name and slug (lowercase)
            name_ratio = difflib.SequenceMatcher(None, anchor_text_lower, cat_key).ratio()
            slug_ratio = difflib.SequenceMatcher(None, anchor_text_lower, cat_data['slug']).ratio()
            current_ratio = max(name_ratio, slug_ratio)

            if current_ratio > best_ratio:
                best_ratio = current_ratio
                best_match_cat = cat_data

        # Optional: Add check for exact substring match if no good fuzzy match
        if not best_match_cat:
             for cat_key, cat_data in category_mapping.items():
                  # Ensure checks are case-insensitive
                  if anchor_text_lower in cat_key.lower() or anchor_text_lower in cat_data['slug'].lower():
                       if len(anchor_text_lower) > 3:
                            log.debug(f"Found substring match for '{anchor_text}' in '{cat_key}' or '{cat_data['slug']}'")
                            return cat_data
        if best_match_cat:
             log.debug(f"Fuzzy matched '{anchor_text}' to category '{best_match_cat['name']}' with ratio {best_ratio:.2f}")
        return best_match_cat
    # --- END NEW ---

    # --- NEW: Process Claude Link Suggestions ---
    def _process_claude_link_suggestions(self, content: str, primary_keyword: str) -> str:
        """Finds link suggestions, matches to categories, converts to links or keeps as suggestions."""
        log.info(f"Processing link suggestions for content related to '{primary_keyword}'...")
        if not content: return ""

        # 1. Fetch Categories and create mapping
        categories = self._fetch_site_categories(taxonomy='product_cat')
        category_mapping = {}
        # Ensure wp_service and api_url_base exist before splitting
        site_url = ""
        if self.wp_service and self.wp_service.api_url_base:
             try:
                 site_url = self.wp_service.api_url_base.split('/wp-json')[0]
             except Exception:
                 log.error("Could not determine site_url from wp_service.api_url_base")

        if categories and site_url:
            for category in categories:
                cat_id = category.get('id')
                name = category.get('name', '').strip() # Keep original case for display
                name_lower = name.lower()
                slug = category.get('slug', '').lower().strip()
                if cat_id and name and slug:
                     cat_url = f"{site_url}/product-category/{slug}/" # Use original slug case for URL if needed
                     cat_data = {'id': cat_id, 'name': name, 'slug': slug, 'url': cat_url}
                     # Map by lower case name and slug
                     category_mapping[name_lower] = cat_data
                     if slug != name_lower: category_mapping[slug] = cat_data
                     # Basic plural/singular variations
                     if name_lower.endswith('s'):
                          singular = name_lower[:-1]
                          if singular not in category_mapping: category_mapping[singular] = cat_data
                     else:
                          plural = name_lower + 's'
                          if plural not in category_mapping: category_mapping[plural] = cat_data
            log.info(f"Created category mapping with {len(category_mapping)} variations.")
        else:
             log.warning("Could not fetch categories or site URL, cannot auto-link suggestions.")

        # 2. Find and Replace Suggestions
        # Use the class="link-opportunity" and data-link-suggestion="..." format
        suggestion_pattern = r'<span class="link-opportunity" data-link-suggestion="([^"]+)">([^<]+)</span>'
        # Need html module for escaping in replacement
        import html

        def replace_match(match):
            suggestion_target = match.group(1)
            anchor_text = match.group(2)

            # Attempt to match anchor text to a category
            matched_category = self._fuzzy_match_category(anchor_text, category_mapping) # Pass self

            if matched_category:
                link_url = matched_category['url']
                log.info(f"Converting suggestion: Found category link for '{anchor_text}' -> {link_url}")
                # Use html.escape on anchor_text just in case it contains special characters
                return f'<a href="{html.escape(link_url)}" class="auto-category-link">{html.escape(anchor_text)}</a>'
            else:
                log.debug(f"Keeping suggestion: No category match for '{anchor_text}' (Suggestion: '{suggestion_target}')")
                # Return the original span, ensuring anchor_text inside is properly escaped
                # It's generally safer to reconstruct it to handle potential HTML injection
                escaped_anchor = html.escape(anchor_text)
                escaped_suggestion = html.escape(suggestion_target)
                return f'<span class="link-opportunity" data-link-suggestion="{escaped_suggestion}">{escaped_anchor}</span>'


        modified_content = re.sub(suggestion_pattern, replace_match, content)
        log.info("Finished processing link suggestions.")
        return modified_content
    # --- END NEW ---

    # --- CORRECTED generate_content ---
    def generate_content(self, brief):
        """Generates content using Claude based on the provided brief AND processes link suggestions.
        Always returns a tuple with (content, error) for consistent handling."""
        if not self.anthropic_client:
            log.error("Anthropic client not available for content generation.")
            return None, "Anthropic client not initialized"

        keyword = brief.get('keyword', 'Unknown Keyword')
        target_w_count = int(brief.get('target_word_count', 1500))

        # 1. Generate the prompt
        prompt = self._generate_claude_prompt(brief)
        if not prompt: # Handle case where prompt generation itself fails
            log.error(f"Prompt generation failed for keyword '{keyword}'")
            return None, "Prompt generation failed"

        # 2. Call Claude API with rate limiting and retries
        self._apply_rate_limiting()
        retries = 0
        content_raw = None # Store the raw content from Claude
        last_error = None
        final_content_for_processing = None # Store the best content we got

        while retries <= self.max_retries:
            try:
                log.info(f"Generating content for '{keyword}' (Attempt {retries+1}/{self.max_retries+1}, Target: {target_w_count} words)")
                system_prompt = f"You are an expert SEO content writer. Write a comprehensive, engaging blog post. CRITICAL: The article MUST be EXACTLY {target_w_count} words long. Use HTML for formatting (h2, h3, p, ul, li, strong). Do not include an H1 title. Start directly with the first H2 section. Count your words."

                message = self.anthropic_client.messages.create(
                    model=self.claude_model,
                    max_tokens=self.claude_max_tokens,
                    temperature=0.3,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
                content_raw = message.content[0].text.strip() # Store raw content
                final_content_for_processing = content_raw # Update best content so far
                actual_w_count = len(content_raw.split())
                log.info(f"Claude generated content with {actual_w_count} words.")

                # Basic validity check
                if actual_w_count < 100 or "sorry" in content_raw.lower()[:100] or "cannot fulfill" in content_raw.lower()[:150]:
                    log.warning("Generated content seems too short or is an error message.")
                    raise ValueError("Generated content potentially invalid or refused.")

                # Word count check
                if actual_w_count >= target_w_count * 0.9:
                    log.info("Content meets word count threshold.")
                    # Link processing happens AFTER successful generation
                    processed_content = self._process_claude_link_suggestions(content_raw, keyword)
                    return processed_content, None # Return PROCESSED content on success
                else:
                    log.warning(f"Generated content word count ({actual_w_count}) is below target ({target_w_count}). Retrying if possible.")
                    last_error = f"Word count {actual_w_count} is less than 90% of target {target_w_count}"
                    # Fall through to retry logic

            # --- Keep existing error handling (APIConnectionError, RateLimitError, etc.) ---
            except anthropic.APIConnectionError as e: 
                last_error = f"Anthropic API conn error: {e}"
                log.warning(last_error)
            except anthropic.RateLimitError as e: 
                last_error = f"Anthropic rate limit exceeded: {e}"
                log.warning(last_error)
                time.sleep((2 ** retries) * 5 + random.uniform(0, 5))
            except anthropic.APIStatusError as e: 
                last_error = f"Anthropic API status error ({e.status_code}): {e.response}"
                log.error(last_error)
                time.sleep(1) # Add small sleep even on non-retryable API errors
            except ValueError as ve: 
                last_error = str(ve)
                log.warning(f"Validation Error: {last_error}")
            except Exception as e: 
                last_error = f"Unexpected error during Claude generation: {str(e)}"
                log.error(last_error, exc_info=True)
            # --- End Error Handling ---

            # Retry logic
            retries += 1
            if retries <= self.max_retries:
                wait_time = (2 ** (retries - 1)) + random.uniform(0, 1)
                log.info(f"Waiting {wait_time:.2f}s before retry...")
                time.sleep(wait_time)
            else:
                log.error(f"Failed to generate content for '{keyword}' that meets criteria after {self.max_retries+1} attempts. Last error: {last_error}")
                # If all retries failed but we got *some* content, process and return it with the error
                if final_content_for_processing:
                    log.warning("Returning last generated content despite failing retries/word count.")
                    processed_content = self._process_claude_link_suggestions(final_content_for_processing, keyword)
                    return processed_content, last_error # Return content but signal the original error
                else:
                    return None, last_error # Failed completely

        return None, "Exceeded max retries" # Should not be reached if loop breaks unexpectedly
    # --- END CORRECTED generate_content ---

    def generate_and_upload_featured_image(self, keyword, content_snippet):
        """Generates and uploads a featured image using Imagen and WordPressService."""
        if not self.imagen_client:
            logging.warning("ImagenClient not available.")
            return None
        if not self.wp_service:
            logging.warning("WordPressService not available for image upload.")
            return None

        try:
            # 1. Build prompt → generate bytes
            prompt_text = self._build_image_prompt(keyword, content_snippet)
            img_bytes   = self.imagen_client.generate_image_bytes(
                prompt_text, n=1, aspect="16:9"
            )[0]

            if not img_bytes:
                logging.error(f"Failed to generate image data for '{keyword}'.")
                return None

            # 2. Upload to WordPress
            image_title = f"Featured image for {keyword}"
            image_data  = BytesIO(img_bytes)

            attachment_id = self.wp_service.upload_image(
                image_data,
                image_title,
                f"{keyword.replace(' ', '-')}.jpg"
            )
            logging.info(f"Uploaded featured image, attachment ID: {attachment_id}")
            return attachment_id

        except Exception as e:
            logging.error(f"Error in image generation/upload process for '{keyword}': {e}", exc_info=True)
            return None

    # --- CORRECTED post_content_to_wordpress ---
    def post_content_to_wordpress(self, brief: Dict, processed_content_result, featured_image_id=None):
        """
        Posts content to WordPress. Handles dual content by saving category description
        to the 'draft' meta field. Properly handles different formats of processed_content_result.
        """
        if not self.wp_service: 
            log.error("WordPressService needed for posting.")
            return None
        if not brief: 
            log.error("Brief data required.")
            return None

        # Handle different formats of processed_content_result properly
        processed_content = None
        generation_error = None
        
        # Check what type of data we received
        if isinstance(processed_content_result, tuple) and len(processed_content_result) == 2:
            # Standard case: tuple with (content, error)
            processed_content, generation_error = processed_content_result
        elif isinstance(processed_content_result, str):
            # Just a string: assume it's content with no error
            processed_content = processed_content_result
            generation_error = None
        else:
            # Unknown format: log error and exit
            log.error(f"Unexpected format for processed_content_result: {type(processed_content_result)}")
            return {
                'category_update': {'status': 'error', 'error': 'Invalid content format'},
                'blog_post': {'status': 'error', 'error': 'Invalid content format'}
            }

        if generation_error and not processed_content: # Complete failure in generation
            log.error(f"Content generation failed completely: {generation_error}")
            # Return error status for both parts
            return {
                'category_update': {'status': 'error', 'error': 'Content generation failed'},
                'blog_post': {'status': 'error', 'error': 'Content generation failed'}
            }

        # If generation had an error but returned partial content (e.g., low word count)
        # We still proceed to post it, but log the original error.
        if generation_error:
            log.warning(f"Posting content generated with error: {generation_error}")

        keyword = brief.get('keyword', 'Unknown Brief')
        recommendation = brief.get('content_recommendation', 'create_new')
        is_dual_content = (recommendation == 'dual_content')
        blog_content = processed_content # Default: assume processed content is the blog post
        category_content_to_save = None
        category_update_result = {'status': 'not_applicable'} # Default
        post_meta_to_save = { # Base meta for the post
            '_content_brief_keyword': keyword,
            '_content_brief_data': json.dumps(brief, default=str), # Serialize full brief
            '_acb_raw_category_content': '',
            '_acb_category_update_status': ''
        }

        # --- Handle Dual Content Parsing & Category Saving ---
        if is_dual_content:
            # Attempt to parse category/blog content from the processed content if markers exist
            category_marker = "=== CATEGORY DESCRIPTION ==="
            blog_marker = "=== BLOG POST ==="
            cat_start = processed_content.find(category_marker)
            blog_start = processed_content.find(blog_marker)

            if cat_start != -1 and blog_start != -1 and blog_start > cat_start:
                log.info("Parsing dual content response based on markers.")
                category_content_to_save = processed_content[cat_start + len(category_marker):blog_start].strip()
                blog_content = processed_content[blog_start + len(blog_marker):].strip() # Override blog_content
                post_meta_to_save['_acb_raw_category_content'] = category_content_to_save # Store raw category content
                log.debug(f"Category content length: {len(category_content_to_save.split())}, Blog content length: {len(blog_content.split())}")
            else:
                log.warning("Dual content markers not found in processed content. Posting all as blog post.")
                is_dual_content = False # Revert to single post flow
                category_content_to_save = None

            # If we successfully parsed category content, try saving it to draft meta
            if is_dual_content and category_content_to_save:
                update_targets = brief.get('update_targets', [])
                if update_targets:
                    target_category = update_targets[0] # Assume first target is the category
                    category_id = target_category.get('id')
                    category_title = target_category.get('title', 'Unknown Category')

                    if category_id and category_id != 'UNKNOWN':
                        try:
                            category_id = int(category_id)
                            draft_meta_key = 'cave_supplies_longform_description_draft'
                            # Add placeholder BEFORE saving to draft
                            blog_reference = f'<p>Learn more about {keyword} in our <a href="BLOG_POST_PLACEHOLDER" class="category-blog-link" data-keyword="{keyword}">detailed guide</a>.</p>'
                            content_with_placeholder = category_content_to_save + "\n\n" + blog_reference

                            log.info(f"Attempting to save description to DRAFT field for category ID: {category_id} ('{category_title}')")
                            # Check if update_term_meta exists on wp_service
                            if hasattr(self.wp_service, 'update_term_meta') and callable(self.wp_service.update_term_meta):
                                updated = self.wp_service.update_term_meta(category_id, draft_meta_key, content_with_placeholder)
                                if updated:
                                    log.info(f"Successfully saved category description to draft meta for category {category_id}.")
                                    category_update_result = {'status': 'draft_saved', 'id': category_id, 'title': category_title}
                                else:
                                    log.error(f"Failed to save category description draft meta for category {category_id} (update_term_meta returned false).")
                                    category_update_result = {'status': 'error', 'id': category_id, 'title': category_title, 'error': 'Failed to update term meta'}
                            else:
                                log.error("WordPressService does not have an 'update_term_meta' method implemented.")
                                category_update_result = {'status': 'error', 'id': category_id, 'title': category_title, 'error': 'update_term_meta method missing'}

                        except ValueError:
                            log.error(f"Invalid category ID format in update_targets: {category_id}")
                            category_update_result = {'status': 'error', 'error': 'Invalid category ID'}
                        except Exception as e_cat_save:
                            log.error(f"Error saving category draft meta for {category_id}: {e_cat_save}", exc_info=True)
                            category_update_result = {'status': 'error', 'id': category_id, 'title': category_title, 'error': f'Exception during meta save: {e_cat_save}'}
                    else:
                        log.warning("Cannot update category draft field: Category ID is missing or UNKNOWN.")
                        category_update_result = {'status': 'error', 'error': 'Missing category ID'}
                else:
                    log.warning("Dual content recommended, but no update_targets found in brief.")
                    category_update_result = {'status': 'error', 'error': 'Missing update_targets'}
        # --- END Dual Content Handling ---

        # --- Create Blog Post ---
        final_result = {'category_update': category_update_result, 'blog_post': {'status': 'pending'}}
        try:
            # Generate simple title
            title = f"{keyword.title()}: The Ultimate Guide"

            # Add category reference link to blog post if dual content was successful so far
            if category_update_result.get('status') == 'draft_saved':
                category_id_for_link = category_update_result.get('id')
                # Attempt to get category slug/URL (needs enhancement in wp_service or use placeholder)
                category_page_url = self.wp_service.get_term_link(category_id_for_link, 'product_cat') # Assumes get_term_link exists
                if category_page_url:
                    category_reference = f'<p>Explore our full collection of <a href="{html.escape(category_page_url)}">{keyword}</a> at Cave Supplies.</p>\n\n'
                    blog_content = category_reference + blog_content
                else:
                    log.warning(f"Could not get URL for category {category_id_for_link} to add link to blog post.")

            post_payload = {
                'title': title,
                'content': blog_content, # Use processed content
                'status': 'draft',
                'comment_status': 'closed',
                'ping_status': 'closed',
                'meta': post_meta_to_save # Use the prepared meta dict
            }
            if featured_image_id:
                post_payload['featured_media'] = featured_image_id

            log.info(f"Creating draft blog post: '{title}'...")
            post_result = self.wp_service.create_post(post_payload, rest_base='posts') # Target 'posts' endpoint

            if post_result and post_result.get('id'):
                post_id = post_result['id']
                post_url = post_result.get('link', '')
                log.info(f"Successfully created draft post ID: {post_id} for keyword '{keyword}'.")
                final_result['blog_post'] = {'status': 'success', 'id': post_id, 'url': post_url}

                # --- Update category draft meta with actual blog post URL ---
                if category_update_result.get('status') == 'draft_saved':
                    category_id_to_update = category_update_result['id']
                    draft_meta_key = 'cave_supplies_longform_description_draft'
                    # Re-fetch content with placeholder or replace in string? Replace is easier if format is known.
                    # Requires the content_with_placeholder variable from earlier block
                    try:
                        # Ensure content_with_placeholder is accessible here (might need refactoring)
                        # For now, assume category_content_to_save holds the text before the placeholder was added
                        blog_reference_updated = f'<p>Learn more about {keyword} in our <a href="{html.escape(post_url)}" class="category-blog-link" data-keyword="{keyword}">detailed guide</a>.</p>'
                        final_category_content = category_content_to_save + "\n\n" + blog_reference_updated

                        log.info(f"Updating category {category_id_to_update} draft meta with final blog post URL.")
                        if hasattr(self.wp_service, 'update_term_meta') and callable(self.wp_service.update_term_meta):
                            if self.wp_service.update_term_meta(category_id_to_update, draft_meta_key, final_category_content):
                                log.info("Successfully updated category draft meta with blog URL.")
                            else:
                                log.error("Failed to update category draft meta with blog URL (update_term_meta returned false).")
                                final_result['category_update']['error'] = final_result['category_update'].get('error', '') + '; Failed URL update'
                        else:
                            log.error("WordPressService does not have 'update_term_meta' method.")
                            final_result['category_update']['error'] = final_result['category_update'].get('error', '') + '; update_term_meta missing'

                    except NameError: # content_with_placeholder might not be defined if initial save failed
                        log.error("Cannot update category placeholder link - initial content variable missing.")
                        final_result['category_update']['error'] = final_result['category_update'].get('error', '') + '; Failed URL update (variable missing)'
                    except Exception as e_update_link:
                        log.error(f"Error updating category placeholder link: {e_update_link}", exc_info=True)
                        final_result['category_update']['error'] = final_result['category_update'].get('error', '') + f'; Failed URL update ({e_update_link})'
                # ---
            else:
                log.error(f"Failed to create WordPress post for keyword '{keyword}'. Response: {post_result}")
                final_result['blog_post'] = {'status': 'error', 'response': post_result}

            return final_result

        except Exception as e:
            log.error(f"Error posting content to WordPress for '{keyword}': {str(e)}", exc_info=True)
            return {'category_update': category_update_result, 'blog_post': {'status': 'error', 'error': str(e)}}
    # --- END REVISED post_content_to_wordpress ---
