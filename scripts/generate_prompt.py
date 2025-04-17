#!/usr/bin/env python3
# generate_prompt.py - Script to generate Claude prompt based on brief ID and recommendation type
# Place this in your PythonAnywhere environment

import os
import sys
import json
import logging
import mysql.connector
import requests
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Optional, List, Any, Union
import time  # For time.sleep

# Add parent directory to the path so we can import cloudways_ip_whitelist
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cloudways_ip_whitelist import whitelist_ip_sync  # Import the whitelisting function

# Load environment variables (.env file should be in parent directory)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_env = load_dotenv(dotenv_path)

# Configure logging
log_dir = os.path.join(os.path.dirname(__file__), '..')
log_file = os.path.join(log_dir, 'prompt_generator.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

def get_db_connection():
    """Establish a connection to the WordPress database."""
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        try:
            conn = mysql.connector.connect(
                host=os.getenv('WP_DB_HOST'),
                user=os.getenv('WP_DB_USER'),
                password=os.getenv('WP_DB_PASSWORD'),
                database=os.getenv('WP_DB_NAME')
            )
            return conn
        except mysql.connector.Error as e:
            # If error is "Can't connect to MySQL server", try whitelisting
            if attempts < max_attempts - 1:
                log.warning(f"Database connection failed: {e}. Attempting to whitelist IP...")
                if whitelist_ip_sync():
                    log.info("IP whitelisted successfully. Retrying connection...")
                else:
                    log.error("IP whitelisting failed.")

            attempts += 1
            if attempts < max_attempts:
                time.sleep(2)  # Wait before retrying
            else:
                log.error(f"Failed to connect to database after {max_attempts} attempts: {e}")
                return None
        except Exception as e:
            log.error(f"Database connection error: {e}")
            return None

def get_wordpress_db_connection():
    """Establish connection to the WordPress database (for briefs)."""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('WP_DB_HOST'),
            user=os.getenv('WP_DB_USER'),
            password=os.getenv('WP_DB_PASSWORD'),
            database=os.getenv('WP_DB_NAME')
        )
        return conn
    except Exception as e:
        log.error(f"WordPress database connection error: {e}")
        return None

def get_category_data(category_id: int) -> Optional[Dict]:
    """Fetch category data from the database."""
    if not category_id:
        return None

    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

        # Query to get category data
        query = f"""
            SELECT t.term_id as id, t.name, t.slug, tt.description
            FROM {prefix}terms AS t
            JOIN {prefix}term_taxonomy AS tt ON t.term_id = tt.term_id
            WHERE t.term_id = %s AND tt.taxonomy = 'product_cat'
        """
        cursor.execute(query, (category_id,))
        category = cursor.fetchone()

        # Get additional meta if needed
        if category:
            # Get category meta including draft content
            meta_query = f"""
                SELECT meta_key, meta_value FROM {prefix}termmeta
                WHERE term_id = %s AND meta_key IN ('_category_description_draft', 'cave_supplies_longform_description_draft')
            """
            cursor.execute(meta_query, (category_id,))
            metas = cursor.fetchall()

            # Add meta to category object
            for meta in metas:
                category[meta['meta_key']] = meta['meta_value']

            # Calculate existing description length
            description = category.get('description', '')
            description_words = len(description.split()) if description else 0
            category['description_word_count'] = description_words

            log.info(f"Found category '{category['name']}' (ID: {category['id']}) with {description_words} words in description")
        else:
            log.warning(f"Category with ID {category_id} not found")

        return category

    except Exception as e:
        log.error(f"Error fetching category data: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_brief_data(brief_id: int) -> Optional[Dict]:
    """Fetch brief data from the WordPress database."""
    if not brief_id:
        return None

    conn = get_wordpress_db_connection()  # Use WordPress connection
    if not conn:
        return None

    try:
        cursor = conn.cursor(dictionary=True)
        prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

        # Query to get post data
        query = f"""
            SELECT ID, post_title, post_content
            FROM {prefix}posts
            WHERE ID = %s AND post_type = 'acb_content_brief'
        """
        cursor.execute(query, (brief_id,))
        brief = cursor.fetchone()

        if not brief:
            log.warning(f"Brief with ID {brief_id} not found")
            return None

        # Get post meta fields
        meta_query = f"""
            SELECT meta_key, meta_value FROM {prefix}postmeta
            WHERE post_id = %s AND meta_key LIKE '\_acb\_%'
        """
        cursor.execute(meta_query, (brief_id,))
        metas = cursor.fetchall()

        # Add meta to brief object
        for meta in metas:
            key = meta['meta_key']
            value = meta['meta_value']
            brief[key] = value

        log.info(f"Found brief '{brief['post_title']}' (ID: {brief['ID']})")
        return brief

    except Exception as e:
        log.error(f"Error fetching brief data: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def generate_prompt(brief_data: Dict, category_data: Optional[Dict] = None) -> Optional[str]:
    """Generate the Claude prompt based on brief and category data."""
    try:
        keyword = brief_data.get('_acb_keyword') or brief_data.get('post_title', 'Unknown')
        target_word_count = int(brief_data.get('_acb_target_word_count', 1500))
        recommendation = brief_data.get('_acb_content_recommendation', 'create_new')
        search_intent = brief_data.get('_acb_search_intent', 'informational')

        # Get keywords, structure, and FAQ data if available
        must_include_phrases = []
        recommended_phrases = []
        content_structure = []
        faq_questions = []

        # Try to get stored keywords/structure if available in meta
        if '_acb_must_include_phrases' in brief_data:
            try:
                must_include_phrases = json.loads(brief_data['_acb_must_include_phrases'])
            except:
                pass

        if '_acb_recommended_phrases' in brief_data:
            try:
                recommended_phrases = json.loads(brief_data['_acb_recommended_phrases'])
            except:
                pass

        if '_acb_content_structure' in brief_data:
            try:
                content_structure = json.loads(brief_data['_acb_content_structure'])
            except:
                pass

        if '_acb_faq_questions' in brief_data:
            try:
                faq_questions = json.loads(brief_data['_acb_faq_questions'])
            except:
                pass

        # Basic structure and intro
        prompt = f"""Please write a comprehensive, SEO-optimized blog article about **"{keyword}"**.

--- Core Article Requirements ---
"""

        # Set up content specs
        content_specs = [
            f"- Primary Keyword Focus: **{keyword}**",
            f"- Search Intent: {search_intent}",
            f"- Target Word Count: **EXACTLY {target_word_count} words** (Strict Requirement)"
        ]

        # Add category-specific information for dual content
        category_word_limit = 500
        dual_content_instructions = ""

        if recommendation == 'dual_content' and category_data:
            content_specs.append(f"- Target word count for category description: 350-{category_word_limit} words")
            content_specs.append(f"- Target word count for blog post: {target_word_count} words")

            cat_name = category_data.get('name', 'Unknown Category')
            cat_id = category_data.get('id', 'Unknown')
            description_word_count = category_data.get('description_word_count', 0)

            content_specs.append(f"- Update the following product category and create a related blog post:")
            content_specs.append(f"  * Category: {cat_name} (ID: {cat_id}, Current description length: {description_word_count} words)")
            content_specs.append(f"- The category description should be concise (350-{category_word_limit} words) and focused on helping shoppers")
            content_specs.append(f"- The blog post should be comprehensive ({target_word_count} words) and educational")
            content_specs.append(f"- Include cross-linking between the category and blog post")

            # Enhanced dual content instructions
            dual_content_instructions = f"""
Special Formatting Instructions for Dual Content:
Please format your response with clear separation between the two content pieces:

=== CATEGORY DESCRIPTION ===
[Category description content here - 350-{category_word_limit} words]

=== BLOG POST ===
[Full blog post content here - target word count as specified ({target_word_count} words)]

For the category description:
- Focus on helping shoppers make purchase decisions for "{keyword}" products
- Keep it concise but informative (350-{category_word_limit} words)
- Highlight key features, benefits, and varieties of "{keyword}" products
- Use persuasive language that encourages purchasing
- Include a brief "Learn more about [{keyword}] in our detailed guide: [BLOG TITLE]" at the end (replace bracketed terms)
- Write directly to customers shopping for these products

For the blog post:
- Create comprehensive, educational content about "{keyword}" ({target_word_count} words)
- Include a "Shop our collection of [{keyword}] at Cave Supplies" link near the beginning or end
- Focus on answering common questions and providing value
- Use proper HTML structure with h2 and h3 headings
"""

        # Add brand context
        brand_context = """
Brand Voice and Context:
- Website: Cave Supplies - online retailer of man cave furniture and home decor (bars, game rooms, home theaters, offices).
- Target Audience: Men personalizing smaller spaces, or those whose partners manage main home decor. Focus on versatility and space-efficiency.
- Mascot (Optional): Thorak, a prehistoric caveman amazed by modern comforts (use sparingly for humor, simple broken sentences: "Thorak like sturdy stool.").
- Tone: Authoritative but approachable and relatable for the target audience. We sell premium products, so avoid overly casual or slang language. Focus on quality, features, benefits, and helping the user create their ideal space.
"""

        # Keyword usage guidelines
        keyword_usage = f"""
Keyword Usage Instructions & Internal Linking:
- **Strict Relevance Required:** Your primary goal is to create the best possible article about **"{keyword}"**.
- Use natural language that reads well to humans while incorporating relevant keywords.
- Include internal link suggestions formatted as follows:
  `<span class="link-opportunity" data-link-suggestion="Describe the ideal target page here">exact phrase to link</span>`
- Example: `...check out our collection of <span class="link-opportunity" data-link-suggestion="Product category page for wooden bar stools">wooden bar stools</span> for a classic look.`
"""

        # Add specific keywords section if available
        if must_include_phrases or recommended_phrases:
            keyword_section = """
--- Provided Keyword Data (Evaluate for Relevance) ---
"""
            if must_include_phrases:
                keyword_section += "Keywords to Include (Primary - Use RELEVANT ones most):\n"
                keyword_section += "\n".join([f"- {kw}" for kw in must_include_phrases[:15]])
                keyword_section += "\n\n"

            if recommended_phrases:
                keyword_section += "Keywords to Consider (Secondary - Use RELEVANT ones):\n"
                keyword_section += "\n".join([f"- {kw}" for kw in recommended_phrases[:30]])
                keyword_section += "\n\n"

            prompt += "\n".join(content_specs) + "\n\n"
            prompt += brand_context + "\n"
            prompt += keyword_usage + "\n"
            prompt += keyword_section
        else:
            # Skip the keywords section if no data
            prompt += "\n".join(content_specs) + "\n\n"
            prompt += brand_context + "\n"
            prompt += keyword_usage + "\n"

        # Add structure if available
        if content_structure:
            structure_section = """
--- Content Structure ---
Suggested Article Structure:
"""
            structure_section += "\n".join([f"{i+1}. {section}" for i, section in enumerate(content_structure)])
            structure_section += "\n\n"
            prompt += structure_section

        # Add FAQs if available
        if faq_questions:
            faq_section = """
--- Frequently Asked Questions ---
Address these questions in your content (preferably in a dedicated FAQ section):
"""
            faq_section += "\n".join([f"- {q}" for q in faq_questions[:10]])
            faq_section += "\n\n"
            prompt += faq_section

        # Add dual content instructions if applicable
        if dual_content_instructions:
            prompt += dual_content_instructions + "\n"

        # Content guidelines
        content_guidelines = f"""
Content & Formatting Guidelines:
- Write comprehensive, valuable, and engaging content focused on **"{keyword}"**. Ensure factual accuracy.
- Use proper HTML: <h2> for main sections (aim for 8-10+ sections to achieve the target word count), <h3> for subsections, <p> for paragraphs, <ul>/<li> for lists, <strong>/<em> for emphasis where appropriate.
- DO NOT include an H1 title tag. Start directly with the first `<h2>` tag.
- Structure content logically using the suggested outline or structure that works best for this topic.
- Use short paragraphs (generally 2-4 sentences) and bullet points for better readability.
- Include a compelling Introduction that hooks the reader and a strong Conclusion that summarizes key takeaways.
- Address relevant FAQs in a dedicated FAQ section near the end using H3 for each question.
- Maintain the Cave Supplies brand voice (authoritative, knowledgeable, helpful, slightly informal but professional, aimed at men building their personal space).
- Mention "Cave Supplies" only 1-2 times max, perhaps in the conclusion as a call to action.
- **Word Count:** The final output MUST be **EXACTLY {target_word_count} words**. Count your words carefully before finishing.
"""

        prompt += content_guidelines + "\n"
        prompt += "Begin the article directly with the first `<h2>` tag."

        # Clean up any double newlines
        prompt = prompt.replace('\n\n\n', '\n\n')

        log.info(f"Generated prompt for '{keyword}' ({len(prompt)} characters)")
        return prompt

    except Exception as e:
        log.error(f"Error generating prompt: {e}")
        return None

def update_brief_prompt(brief_id: int, prompt: str) -> bool:
    """Update the prompt in the database for a brief."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

        # Check if meta exists
        cursor.execute(
            f"SELECT meta_id FROM {prefix}postmeta WHERE post_id = %s AND meta_key = %s",
            (brief_id, '_acb_claude_prompt')
        )
        meta_exists = cursor.fetchone()

        if meta_exists:
            cursor.execute(
                f"UPDATE {prefix}postmeta SET meta_value = %s WHERE post_id = %s AND meta_key = %s",
                (prompt, brief_id, '_acb_claude_prompt')
            )
        else:
            cursor.execute(
                f"INSERT INTO {prefix}postmeta (post_id, meta_key, meta_value) VALUES (%s, %s, %s)",
                (brief_id, '_acb_claude_prompt', prompt)
            )

        conn.commit()
        log.info(f"Updated prompt for brief ID {brief_id}")
        return True

    except Exception as e:
        log.error(f"Error updating brief prompt: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def respond_with_json(success: bool, message: Optional[str] = None, prompt: Optional[str] = None, prompt_length: int = 0):
    """Return a JSON response for API or CLI use."""
    response = {
        'success': success
    }

    if message:
        response['message'] = message

    if prompt:
        response['prompt'] = prompt
        response['prompt_length'] = prompt_length
    elif prompt_length:
        response['prompt_length'] = prompt_length

    print(json.dumps(response))
    sys.exit(0 if success else 1)

def main():
    """Main function that handles both CLI and API usage."""
    try:
        # Check if running as CGI script
        is_cgi = 'REQUEST_METHOD' in os.environ

        if is_cgi:
            # Running as CGI script
            import cgi

            # Output headers
            print("Content-Type: application/json")
            print("")

            # Parse form data
            form = cgi.FieldStorage()
            brief_id = int(form.getvalue('brief_id', 0))
            recommendation = form.getvalue('recommendation', 'create_new')
            category_id = int(form.getvalue('category_id', 0)) if form.getvalue('category_id') else 0
        else:
            # Running from command line
            if len(sys.argv) < 2:
                respond_with_json(False, "Missing arguments. Usage: generate_prompt.py <brief_id> [recommendation] [category_id]")

            brief_id = int(sys.argv[1])
            recommendation = sys.argv[2] if len(sys.argv) > 2 else 'create_new'
            category_id = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 0

        # Validate inputs
        if not brief_id:
            respond_with_json(False, "Invalid brief ID")

        if recommendation not in ['create_new', 'dual_content']:
            respond_with_json(False, "Invalid recommendation type")

        if recommendation == 'dual_content' and not category_id:
            respond_with_json(False, "Category ID is required for dual content")

        # Get brief data
        brief_data = get_brief_data(brief_id)
        if not brief_data:
            respond_with_json(False, f"Brief with ID {brief_id} not found")

        # Get category data if needed
        category_data = None
        if recommendation == 'dual_content' and category_id:
            category_data = get_category_data(category_id)
            if not category_data:
                respond_with_json(False, f"Category with ID {category_id} not found")

        # Generate prompt
        prompt = generate_prompt(brief_data, category_data)
        if not prompt:
            respond_with_json(False, "Failed to generate prompt")

        # Update the brief with the new prompt
        success = update_brief_prompt(brief_id, prompt)
        if not success:
            respond_with_json(False, "Failed to update brief with new prompt")

        # Also update the recommendation and category ID if needed
        if success:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    prefix = os.getenv('WP_TABLE_PREFIX', 'wp_')

                    # Update content recommendation
                    cursor.execute(
                        f"UPDATE {prefix}postmeta SET meta_value = %s WHERE post_id = %s AND meta_key = %s",
                        (recommendation, brief_id, '_acb_content_recommendation')
                    )

                    # Update category ID if dual content
                    if recommendation == 'dual_content' and category_id:
                        # Check if meta exists
                        cursor.execute(
                            f"SELECT meta_id FROM {prefix}postmeta WHERE post_id = %s AND meta_key = %s",
                            (brief_id, '_acb_target_category_id')
                        )
                        meta_exists = cursor.fetchone()

                        if meta_exists:
                            cursor.execute(
                                f"UPDATE {prefix}postmeta SET meta_value = %s WHERE post_id = %s AND meta_key = %s",
                                (str(category_id), brief_id, '_acb_target_category_id')
                            )
                        else:
                            cursor.execute(
                                f"INSERT INTO {prefix}postmeta (post_id, meta_key, meta_value) VALUES (%s, %s, %s)",
                                (brief_id, '_acb_target_category_id', str(category_id))
                            )

                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()

        # Return success
        respond_with_json(True, "Prompt generated and updated successfully", prompt, len(prompt))

    except Exception as e:
        log.error(f"Error in main function: {e}")
        respond_with_json(False, f"Error: {str(e)}")

if __name__ == "__main__":
    main()