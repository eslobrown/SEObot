# app.py
import os
import logging
from flask import Flask, request, jsonify
import config # Import config to access variables
import database # Import database functions
import sys
from cloudways_ip_whitelist import whitelist_ip_sync

# Add this code before creating the Flask app or handling requests
try:
    # Whitelist the current IP address for MySQL access
    if not whitelist_ip_sync():
        logging.error("Failed to whitelist IP for Cloudways MySQL access. Database operations may fail.")
    else:
        logging.info("Successfully whitelisted IP for Cloudways MySQL access")
except Exception as e:
    logging.error(f"Error during IP whitelisting: {e}")

# Configure logging
log = logging.getLogger(__name__)
log.setLevel(logging.INFO) # Or DEBUG for more details

app = Flask(__name__)
# Load a secret key for Flask session security (optional but recommended)
app.config['SECRET_KEY'] = config.FLASK_APP_SECRET_KEY

# --- Helper for Authentication ---
def is_request_authenticated(request):
    """Validates the incoming request using the shared secret token."""
    provided_token = request.headers.get('X-Plugin-Token')
    if not provided_token:
        log.warning("Webhook request missing X-Plugin-Token header.")
        return False
    if provided_token == config.WP_PLUGIN_SECRET_TOKEN:
        return True
    else:
        log.warning("Webhook request received with invalid token.")
        return False

# --- Webhook Endpoint ---
@app.route('/trigger-generation', methods=['POST'])
def trigger_generation():
    """
    Webhook endpoint to receive content generation requests from WordPress.
    Adds the task to the database queue.
    """
    log.info("Received request on /trigger-generation")

    # 1. Authentication
    if not is_request_authenticated(request):
        log.warning("Authentication failed for /trigger-generation request.")
        return jsonify({"status": "error", "message": "Authentication failed"}), 403

    # 2. Validate Input
    if not request.is_json:
        log.error("Invalid request: Content-Type must be application/json.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    log.debug(f"Received data: {data}")

    required_fields = ['brief_id', 'prompt', 'target_word_count', 'keyword', 'callback_url']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        msg = f"Missing required fields: {', '.join(missing_fields)}"
        log.error(msg)
        return jsonify({"status": "error", "message": msg}), 400

    # 3. Add Task to Queue
    try:
        task_payload = {
            'brief_id': data['brief_id'],
            'prompt': data['prompt'],
            'target_word_count': data['target_word_count'],
            'keyword': data['keyword'],
            'callback_url': data['callback_url']
            # Add any other relevant data needed by the worker
        }
        task_id = database.add_task(task_type='generate_content', payload=task_payload)

        if task_id:
            log.info(f"Successfully queued task {task_id} for brief ID {data['brief_id']}")
            return jsonify({"status": "queued", "task_id": task_id}), 202 # 202 Accepted
        else:
            log.error(f"Failed to add task to database for brief ID {data['brief_id']}")
            return jsonify({"status": "error", "message": "Failed to queue task"}), 500

    except Exception as e:
        log.exception(f"Unexpected error processing /trigger-generation request: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

# --- Root Endpoint (Optional - for health check) ---
@app.route('/')
def index():
    # Simple health check endpoint
    return jsonify({"status": "ok", "message": "Content Generation Backend is running."}), 200

# --- Run Flask App (for local testing) ---
# On PythonAnywhere, you'll configure this via the WSGI file, not run it directly.
if __name__ == '__main__':
    log.info("Starting Flask development server...")
    # Use 0.0.0.0 to be accessible on network if needed, default port 5000
    # Set debug=True ONLY for development, NEVER for production
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)

# --- Prompt Generation Endpoint ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt_endpoint():
    """
    Webhook endpoint to generate a Claude prompt based on brief parameters.
    """
    log.info("Received request on /generate-prompt")

    # 1. Authentication
    if not is_request_authenticated(request):
        log.warning("Authentication failed for /generate-prompt request.")
        return jsonify({"status": "error", "message": "Authentication failed"}), 403

    # 2. Validate Input
    if not request.is_json:
        log.error("Invalid request: Content-Type must be application/json.")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    log.debug(f"Received data: {data}")

    required_fields = ['brief_id', 'recommendation']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        msg = f"Missing required fields: {', '.join(missing_fields)}"
        log.error(msg)
        return jsonify({"status": "error", "message": msg}), 400

    # 3. Process the request
    try:
        brief_id = data['brief_id']
        recommendation = data['recommendation']
        category_id = data.get('category_id', 0)

        # Use our imported script functions
        sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
        from scripts.generate_prompt import get_brief_data, get_category_data, generate_prompt, update_brief_prompt

        # Get data and generate prompt
        brief_data = get_brief_data(brief_id)
        if not brief_data:
            return jsonify({"status": "error", "message": f"Brief with ID {brief_id} not found"}), 404

        category_data = None
        if recommendation == 'dual_content' and category_id:
            category_data = get_category_data(category_id)
            if not category_data and category_id > 0:
                return jsonify({"status": "error", "message": f"Category with ID {category_id} not found"}), 404

        prompt = generate_prompt(brief_data, category_data)
        if not prompt:
            return jsonify({"status": "error", "message": "Failed to generate prompt"}), 500

        # Update the brief with the new prompt
        success = update_brief_prompt(brief_id, prompt)
        if not success:
            return jsonify({"status": "error", "message": "Generated prompt but failed to update brief"}), 500

        # Return success with the generated prompt
        return jsonify({
            "status": "success",
            "message": "Prompt generated successfully",
            "prompt": prompt,
            "prompt_length": len(prompt)
        }), 200

    except Exception as e:
        log.exception(f"Error processing /generate-prompt request: {e}")
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500
