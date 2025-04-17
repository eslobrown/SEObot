<?php
/**
 * Handles AJAX requests for the plugin.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * AJAX handler for approving a content brief.
 */
function acb_ajax_approve_brief_handler() {
    // 1. Verify Nonce
    $nonce = isset($_POST['_ajax_nonce']) ? sanitize_key($_POST['_ajax_nonce']) : '';
    $brief_id = isset($_POST['brief_id']) ? intval($_POST['brief_id']) : 0;

    if (!$brief_id || !wp_verify_nonce($nonce, 'acb_approve_brief_' . $brief_id)) {
        wp_send_json_error(array('message' => __('Security check failed.', 'ai-content-briefs')), 403);
    }

    // 2. Check User Capabilities
    if (!current_user_can('edit_post', $brief_id)) {
        wp_send_json_error(array('message' => __('You do not have permission to approve this brief.', 'ai-content-briefs')), 403);
    }

    // 3. Perform Action
    $current_status = get_post_meta($brief_id, '_acb_status', true);

    // Allow approval if pending or error
    if (in_array($current_status, ['pending', 'error', ''])) {
        $updated = update_post_meta($brief_id, '_acb_status', 'approved');

        if ($updated) {
            // Now trigger the same generation workflow as we added to the status update handler
            // Get required data for generation
            $prompt = get_post_meta($brief_id, '_acb_claude_prompt', true);
            $target_wc = get_post_meta($brief_id, '_acb_target_word_count', true);
            $keyword = get_post_meta($brief_id, '_acb_keyword', true);
            
            // Fallback to title if keyword meta is empty
            if (empty($keyword)) {
                $keyword = get_the_title($brief_id);
            }

            if (empty($prompt) || empty($target_wc) || empty($keyword)) {
                // Prepare the updated status HTML to send back to JS
                $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                    esc_attr('status-approved'),
                    esc_attr('color: #0073aa; font-weight: bold;'),
                    esc_html(__('Approved', 'ai-content-briefs'))
                );
                
                wp_send_json_success(array(
                    'message' => __('Brief approved, but missing required data for generation.', 'ai-content-briefs'),
                    'status_html' => $status_html
                ));
                return;
            }

            // Get Settings
            $options = get_option('acb_settings');
            $webhook_url = isset($options['acb_webhook_url']) ? esc_url_raw($options['acb_webhook_url']) : '';
            $secret_token = isset($options['acb_secret_token']) ? sanitize_text_field($options['acb_secret_token']) : '';

            if (empty($webhook_url) || empty($secret_token)) {
                // Just return success with approved status
                $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                    esc_attr('status-approved'),
                    esc_attr('color: #0073aa; font-weight: bold;'),
                    esc_html(__('Approved', 'ai-content-briefs'))
                );
                
                wp_send_json_success(array(
                    'message' => __('Brief approved, but plugin settings not configured for generation.', 'ai-content-briefs'),
                    'status_html' => $status_html
                ));
                return;
            }

            // Define Callback URL
            $callback_url = rest_url('ai-content-briefs/v1/generation-callback');

            // Prepare Payload
            $payload = array(
                'brief_id'          => $brief_id,
                'prompt'            => $prompt,
                'target_word_count' => (int) $target_wc,
                'keyword'           => $keyword,
                'callback_url'      => $callback_url
            );

            // Send Webhook Request
            $args = array(
                'method'    => 'POST',
                'timeout'   => 15,
                'headers'   => array(
                    'Content-Type' => 'application/json; charset=utf-8',
                    'X-Plugin-Token' => $secret_token,
                ),
                'body'      => wp_json_encode($payload),
                'data_format' => 'body',
            );

            $response = wp_remote_post($webhook_url, $args);

            if (is_wp_error($response)) {
                // Prepare approved status HTML but report error
                $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                    esc_attr('status-approved'),
                    esc_attr('color: #0073aa; font-weight: bold;'),
                    esc_html(__('Approved', 'ai-content-briefs'))
                );
                
                wp_send_json_success(array(
                    'message' => __('Brief approved, but failed to queue generation: ', 'ai-content-briefs') . ' ' . $response->get_error_message(),
                    'status_html' => $status_html
                ));
                return;
            }

            $status_code = wp_remote_retrieve_response_code($response);
            $body = wp_remote_retrieve_body($response);
            $response_data = json_decode($body, true);

            if ($status_code === 202 && isset($response_data['status']) && $response_data['status'] === 'queued') {
                // SUCCESS: Task was queued
                update_post_meta($brief_id, '_acb_status', 'generating');
                if (isset($response_data['task_id'])) {
                    update_post_meta($brief_id, '_acb_pa_task_id', sanitize_text_field($response_data['task_id']));
                }

                // Prepare updated generating status HTML
                $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                    esc_attr('status-generating'),
                    esc_attr('color: #ffb900;'),
                    esc_html(__('Generating', 'ai-content-briefs'))
                );
                
                wp_send_json_success(array(
                    'message' => __('Brief approved and content generation automatically triggered.', 'ai-content-briefs'),
                    'status_html' => $status_html,
                    'task_id' => isset($response_data['task_id']) ? $response_data['task_id'] : null
                ));
                return;
            } else {
                // Error from PythonAnywhere - keep as approved but show error
                $error_message = isset($response_data['message']) ? $response_data['message'] : $body;
                
                $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                    esc_attr('status-approved'),
                    esc_attr('color: #0073aa; font-weight: bold;'),
                    esc_html(__('Approved', 'ai-content-briefs'))
                );
                
                wp_send_json_success(array(
                    'message' => __('Brief approved, but generation service returned an error:', 'ai-content-briefs') . ' (' . $status_code . ') ' . esc_html($error_message),
                    'status_html' => $status_html
                ));
                return;
            }
        } else {
            // This might happen if the value was already 'approved' or DB error
            wp_send_json_error(array('message' => __('Could not update brief status. It might already be approved.', 'ai-content-briefs')));
        }
    } else {
        wp_send_json_error(array('message' => __('Brief cannot be approved from its current status.', 'ai-content-briefs') . ' (' . $current_status . ')'));
    }
}
// Hook for logged-in users
add_action( 'wp_ajax_acb_approve_brief', 'acb_ajax_approve_brief_handler' );


/**
 * AJAX handler for triggering content generation.
 */
function acb_ajax_generate_content_handler() {
    // 1. Verify Nonce
    $nonce = isset( $_POST['_ajax_nonce'] ) ? sanitize_key( $_POST['_ajax_nonce'] ) : '';
    $brief_id = isset( $_POST['brief_id'] ) ? intval( $_POST['brief_id'] ) : 0;

    if ( ! $brief_id || ! wp_verify_nonce( $nonce, 'acb_generate_content_' . $brief_id ) ) {
         wp_send_json_error( array( 'message' => __( 'Security check failed.', 'ai-content-briefs' ) ), 403 );
    }

    // 2. Check User Capabilities
    if ( ! current_user_can( 'edit_post', $brief_id ) ) {
         wp_send_json_error( array( 'message' => __( 'You do not have permission to generate content for this brief.', 'ai-content-briefs' ) ), 403 );
    }

    // 3. Check Status (Should be 'approved')
    $current_status = get_post_meta( $brief_id, '_acb_status', true );
    if ( $current_status !== 'approved' ) {
         wp_send_json_error( array( 'message' => __( 'Content can only be generated for approved briefs.', 'ai-content-briefs' ) ) );
    }

    // 4. Get Required Data for Webhook
    $prompt = get_post_meta( $brief_id, '_acb_claude_prompt', true );
    $target_wc = get_post_meta( $brief_id, '_acb_target_word_count', true );
    $keyword = get_post_meta( $brief_id, '_acb_keyword', true ); // Use keyword meta field
    // Fallback to title if keyword meta is empty
    if(empty($keyword)) {
        $keyword = get_the_title($brief_id);
    }


    if ( empty( $prompt ) || empty( $target_wc ) || empty( $keyword ) ) {
         wp_send_json_error( array( 'message' => __( 'Brief is missing required data (prompt, target word count, or keyword) for generation.', 'ai-content-briefs' ) ) );
    }

    // 5. Get Settings (Webhook URL, Secret Token)
    $options = get_option( 'acb_settings' ); // We'll create settings later
    $webhook_url = isset( $options['acb_webhook_url'] ) ? esc_url_raw( $options['acb_webhook_url'] ) : '';
    $secret_token = isset( $options['acb_secret_token'] ) ? sanitize_text_field( $options['acb_secret_token'] ) : '';

    if ( empty( $webhook_url ) || empty( $secret_token ) ) {
         wp_send_json_error( array( 'message' => __( 'Plugin settings (Webhook URL or Secret Token) are not configured.', 'ai-content-briefs' ) ) );
    }

    // 6. Define Callback URL
    $callback_url = rest_url( 'ai-content-briefs/v1/generation-callback' ); // Use rest_url() helper

    // 7. Prepare Payload for PythonAnywhere
    $payload = array(
        'brief_id'          => $brief_id,
        'prompt'            => $prompt,
        'target_word_count' => (int) $target_wc,
        'keyword'           => $keyword,
        'callback_url'      => $callback_url
        // Add any other necessary data
    );

    // 8. Send Webhook Request using wp_remote_post
    $args = array(
        'method'    => 'POST',
        'timeout'   => 15, // Short timeout - we just need PA to acknowledge receipt
        'headers'   => array(
            'Content-Type' => 'application/json; charset=utf-8',
            'X-Plugin-Token' => $secret_token, // Send the secret token
        ),
        'body'      => wp_json_encode( $payload ), // Encode payload as JSON
        'data_format' => 'body',
    );

    $response = wp_remote_post( $webhook_url, $args );

    // 9. Handle Response from PythonAnywhere
    if ( is_wp_error( $response ) ) {
        // Network error or similar WP_Error
        wp_send_json_error( array( 'message' => __( 'Failed to send request to generation service:', 'ai-content-briefs' ) . ' ' . $response->get_error_message() ) );
    } else {
        $status_code = wp_remote_retrieve_response_code( $response );
        $body = wp_remote_retrieve_body( $response );
        $response_data = json_decode( $body, true );

        if ( $status_code === 202 && isset($response_data['status']) && $response_data['status'] === 'queued' ) {
            // SUCCESS: Task was queued by PythonAnywhere
            update_post_meta( $brief_id, '_acb_status', 'generating' );
            if (isset($response_data['task_id'])) {
                 update_post_meta( $brief_id, '_acb_pa_task_id', sanitize_text_field($response_data['task_id']) );
            }

            // Prepare updated status HTML
            $status_html = sprintf('<span class="acb-status %s" style="%s">%s</span>',
                esc_attr('status-generating'),
                esc_attr('color: #ffb900;'), // Style from list table class
                esc_html(__( 'Generating', 'ai-content-briefs' ))
            );

            wp_send_json_success( array(
                'message' => __( 'Content generation task queued.', 'ai-content-briefs' ),
                'status_html' => $status_html,
                'task_id' => isset($response_data['task_id']) ? $response_data['task_id'] : null
             ) );
        } else {
            // Error response from PythonAnywhere
            $error_message = isset( $response_data['message'] ) ? $response_data['message'] : $body;
             wp_send_json_error( array( 'message' => __( 'Generation service returned an error:', 'ai-content-briefs' ) . ' (' . $status_code . ') ' . esc_html($error_message) ) );
        }
    }

     // Should not reach here
     wp_die();
}
// Hook for logged-in users
add_action( 'wp_ajax_acb_generate_content', 'acb_ajax_generate_content_handler' );

// --- !!! NEW: AJAX Handler for Updating Status via Dropdown !!! ---
/**
 * AJAX handler for updating brief status from the list table dropdown.
 */
function acb_ajax_update_status_handler() {
    // 1. Verify Nonce & Get Data
    $brief_id = isset($_POST['brief_id']) ? intval($_POST['brief_id']) : 0;
    $nonce = isset($_POST['_ajax_nonce']) ? sanitize_key($_POST['_ajax_nonce']) : '';
    $new_status = isset($_POST['new_status']) ? sanitize_text_field($_POST['new_status']) : '';

    if (!$brief_id || !wp_verify_nonce($nonce, 'acb_update_status_' . $brief_id) || !$new_status) {
        wp_send_json_error(array('message' => __('Security check failed or missing data.', 'ai-content-briefs')), 403);
    }

    // 2. Check User Capabilities
    if (!current_user_can('edit_post', $brief_id)) {
        wp_send_json_error(array('message' => __('You do not have permission to update this brief.', 'ai-content-briefs')), 403);
    }

    // 3. Validate New Status
    $valid_statuses = array(
        'pending', 'approved', 'generating', 'draft_ready', 'published', 'error', 'skip'
    );
    if (!in_array($new_status, $valid_statuses)) {
        wp_send_json_error(array('message' => __('Invalid status value provided.', 'ai-content-briefs')));
    }

    // 4. Prevent changing FROM 'generating' state
    $current_status = get_post_meta($brief_id, '_acb_status', true);
    if ($current_status === 'generating' && $new_status !== 'generating') {
        wp_send_json_error(array('message' => __('Cannot manually change status away from "Generating".', 'ai-content-briefs')));
    }

    $updated = update_post_meta($brief_id, '_acb_status', $new_status);

    // 5. Auto-queue generation task if status was changed TO 'approved'
    if ($updated !== false && $new_status === 'approved' && $current_status !== 'approved') {
        // Get required data for generation
        $prompt = get_post_meta($brief_id, '_acb_claude_prompt', true);
        $target_wc = get_post_meta($brief_id, '_acb_target_word_count', true);
        $keyword = get_post_meta($brief_id, '_acb_keyword', true);
        
        // Fallback to title if keyword meta is empty
        if (empty($keyword)) {
            $keyword = get_the_title($brief_id);
        }

        if (empty($prompt) || empty($target_wc) || empty($keyword)) {
            wp_send_json_error(array(
                'message' => __('Status updated to "approved", but brief is missing required data (prompt, target word count, or keyword) for generation.', 'ai-content-briefs')
            ));
            return;
        }

        // Get Settings (Webhook URL, Secret Token)
        $options = get_option('acb_settings');
        $webhook_url = isset($options['acb_webhook_url']) ? esc_url_raw($options['acb_webhook_url']) : '';
        $secret_token = isset($options['acb_secret_token']) ? sanitize_text_field($options['acb_secret_token']) : '';

        if (empty($webhook_url) || empty($secret_token)) {
            wp_send_json_error(array(
                'message' => __('Status updated to "approved", but plugin settings (Webhook URL or Secret Token) are not configured.', 'ai-content-briefs')
            ));
            return;
        }

        // Define Callback URL
        $callback_url = rest_url('ai-content-briefs/v1/generation-callback');

        // Prepare Payload for PythonAnywhere
        $payload = array(
            'brief_id'          => $brief_id,
            'prompt'            => $prompt,
            'target_word_count' => (int) $target_wc,
            'keyword'           => $keyword,
            'callback_url'      => $callback_url
        );

        // Send Webhook Request
        $args = array(
            'method'    => 'POST',
            'timeout'   => 15,
            'headers'   => array(
                'Content-Type' => 'application/json; charset=utf-8',
                'X-Plugin-Token' => $secret_token,
            ),
            'body'      => wp_json_encode($payload),
            'data_format' => 'body',
        );

        $response = wp_remote_post($webhook_url, $args);

        if (is_wp_error($response)) {
            update_post_meta($brief_id, '_acb_status', 'error');
            update_post_meta($brief_id, '_acb_error_message', $response->get_error_message());
            wp_send_json_error(array(
                'message' => __('Failed to queue generation task:', 'ai-content-briefs') . ' ' . $response->get_error_message()
            ));
            return;
        }

        $status_code = wp_remote_retrieve_response_code($response);
        $body = wp_remote_retrieve_body($response);
        $response_data = json_decode($body, true);

        if ($status_code === 202 && isset($response_data['status']) && $response_data['status'] === 'queued') {
            // SUCCESS: Task was queued
            update_post_meta($brief_id, '_acb_status', 'generating');
            if (isset($response_data['task_id'])) {
                update_post_meta($brief_id, '_acb_pa_task_id', sanitize_text_field($response_data['task_id']));
            }
            wp_send_json_success(array(
                'message' => __('Status updated and content generation task automatically queued.', 'ai-content-briefs'),
                'task_id' => isset($response_data['task_id']) ? $response_data['task_id'] : null
            ));
            return;
        } else {
            // Error response from PythonAnywhere
            $error_message = isset($response_data['message']) ? $response_data['message'] : $body;
            update_post_meta($brief_id, '_acb_status', 'error');
            update_post_meta($brief_id, '_acb_error_message', $error_message);
            wp_send_json_error(array(
                'message' => __('Status updated to "approved", but generation service returned an error:', 'ai-content-briefs') . ' (' . $status_code . ') ' . esc_html($error_message)
            ));
            return;
        }
    }

    if ($updated !== false) {
        wp_send_json_success(array('message' => __('Status updated successfully.', 'ai-content-briefs')));
    } else {
        wp_send_json_error(array('message' => __('Could not update brief status. It might already be set to this value.', 'ai-content-briefs')));
    }
}

/**
 * AJAX handler for updating the Claude prompt based on content recommendation.
 */
function acb_ajax_update_prompt_handler() {
    // Verify nonce
    if (!isset($_POST['_ajax_nonce']) || !wp_verify_nonce(sanitize_key($_POST['_ajax_nonce']), 'acb_update_prompt_nonce')) {
        wp_send_json_error(array('message' => __('Security check failed.', 'ai-content-briefs')));
    }

    // Check permissions
    if (!current_user_can('edit_posts')) {
        wp_send_json_error(array('message' => __('You do not have permission to update prompts.', 'ai-content-briefs')));
    }

    // Get parameters
    $brief_id = isset($_POST['brief_id']) ? intval($_POST['brief_id']) : 0;
    $recommendation = isset($_POST['recommendation']) ? sanitize_text_field($_POST['recommendation']) : 'create_new';
    $category_id = isset($_POST['category_id']) ? intval($_POST['category_id']) : 0;

    if (!$brief_id) {
        wp_send_json_error(array('message' => __('Invalid brief ID.', 'ai-content-briefs')));
    }

    // Verify recommendation
    if (!in_array($recommendation, array('create_new', 'dual_content'))) {
        wp_send_json_error(array('message' => __('Invalid recommendation type.', 'ai-content-briefs')));
    }

    // Verify category ID for dual content
    if ($recommendation === 'dual_content' && empty($category_id)) {
        wp_send_json_error(array('message' => __('Category ID is required for dual content.', 'ai-content-briefs')));
    }

    // Save settings first 
    update_post_meta($brief_id, '_acb_content_recommendation', $recommendation);
    if ($recommendation === 'dual_content') {
        update_post_meta($brief_id, '_acb_target_category_id', $category_id);
    }

    // Call the Python script to generate a new prompt
    $result = acb_call_prompt_generator($brief_id, $recommendation, $category_id);

    if ($result['success']) {
        wp_send_json_success(array(
            'message' => __('Prompt updated successfully!', 'ai-content-briefs'),
            'prompt_length' => $result['prompt_length']
        ));
    } else {
        wp_send_json_error(array('message' => $result['message']));
    }
}
add_action('wp_ajax_acb_update_prompt', 'acb_ajax_update_prompt_handler');

/**
 * Call the Python script to generate a new Claude prompt.
 * This can be implemented in different ways depending on your environment.
 */
function acb_call_prompt_generator($brief_id, $recommendation, $category_id = 0) {
    // Option 1: Call a separate Python REST API endpoint (recommended)
    $options = get_option('acb_settings');
    $prompt_generator_url = isset($options['acb_prompt_generator_url']) ? esc_url_raw($options['acb_prompt_generator_url']) : '';
    $secret_token = isset($options['acb_secret_token']) ? $options['acb_secret_token'] : '';
    
    if (empty($prompt_generator_url)) {
        return array(
            'success' => false,
            'message' => __('Prompt generator URL not configured in settings.', 'ai-content-briefs')
        );
    }
    
    // Get brief data to send to the prompt generator
    $brief_data = array(
        'brief_id' => $brief_id,
        'title' => get_the_title($brief_id),
        'recommendation' => $recommendation,
        'category_id' => $category_id,
        // Include other meta fields needed for prompt generation
        'target_word_count' => get_post_meta($brief_id, '_acb_target_word_count', true),
        'search_intent' => get_post_meta($brief_id, '_acb_search_intent', true),
        'keyword' => get_post_meta($brief_id, '_acb_keyword', true) ?: get_the_title($brief_id)
    );
    
    $response = wp_remote_post($prompt_generator_url, array(
        'timeout' => 30,
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Plugin-Token' => $secret_token
        ),
        'body' => wp_json_encode($brief_data)
    ));
    
    if (is_wp_error($response)) {
        return array(
            'success' => false,
            'message' => sprintf(__('Error connecting to prompt generator: %s', 'ai-content-briefs'), $response->get_error_message())
        );
    }
    
    $status_code = wp_remote_retrieve_response_code($response);
    $body = wp_remote_retrieve_body($response);
    $data = json_decode($body, true);
    
    if ($status_code !== 200 || !isset($data['prompt'])) {
        return array(
            'success' => false,
            'message' => sprintf(__('Error from prompt generator (%d): %s', 'ai-content-briefs'), 
                               $status_code, isset($data['message']) ? $data['message'] : __('Unknown error', 'ai-content-briefs'))
        );
    }
    
    // Save the new prompt
    update_post_meta($brief_id, '_acb_claude_prompt', $data['prompt']);
    
    return array(
        'success' => true,
        'prompt_length' => strlen($data['prompt'])
    );
    
    // Option 2 (alternative): Direct shell_exec to a Python script (less recommended)
    /*
    $python_path = '/usr/bin/python3'; // Adjust to your system
    $script_path = plugin_dir_path(dirname(__FILE__)) . 'scripts/generate_prompt.py';
    
    // Escape all arguments for shell safety
    $escaped_args = escapeshellarg($brief_id) . ' ' . 
                   escapeshellarg($recommendation) . ' ' . 
                   escapeshellarg($category_id);
    
    $command = "$python_path $script_path $escaped_args";
    
    // Execute the command
    $output = shell_exec($command);
    $result = json_decode($output, true);
    
    if ($result && isset($result['prompt'])) {
        update_post_meta($brief_id, '_acb_claude_prompt', $result['prompt']);
        return array(
            'success' => true,
            'prompt_length' => strlen($result['prompt'])
        );
    }
    
    return array(
        'success' => false,
        'message' => __('Failed to generate prompt using Python script.', 'ai-content-briefs')
    );
    */
}

/**
 * Helper function to trigger content generation for a brief.
 * 
 * @param int $brief_id The ID of the brief to generate content for.
 * @return bool|string True on success, error message on failure.
 */
function acb_trigger_content_generation($brief_id) {
    // Get required data for generation
    $prompt = get_post_meta($brief_id, '_acb_claude_prompt', true);
    $target_wc = get_post_meta($brief_id, '_acb_target_word_count', true);
    $keyword = get_post_meta($brief_id, '_acb_keyword', true);
    
    // Fallback to title if keyword meta is empty
    if (empty($keyword)) {
        $keyword = get_the_title($brief_id);
    }

    if (empty($prompt) || empty($target_wc) || empty($keyword)) {
        return "Missing required data (prompt, target word count, or keyword)";
    }

    // Get Settings
    $options = get_option('acb_settings');
    $webhook_url = isset($options['acb_webhook_url']) ? esc_url_raw($options['acb_webhook_url']) : '';
    $secret_token = isset($options['acb_secret_token']) ? sanitize_text_field($options['acb_secret_token']) : '';

    if (empty($webhook_url) || empty($secret_token)) {
        return "Plugin settings (Webhook URL or Secret Token) not configured";
    }

    // Define Callback URL
    $callback_url = rest_url('ai-content-briefs/v1/generation-callback');

    // Prepare Payload
    $payload = array(
        'brief_id'          => $brief_id,
        'prompt'            => $prompt,
        'target_word_count' => (int) $target_wc,
        'keyword'           => $keyword,
        'callback_url'      => $callback_url
    );

    // Send Webhook Request
    $args = array(
        'method'    => 'POST',
        'timeout'   => 15,
        'headers'   => array(
            'Content-Type' => 'application/json; charset=utf-8',
            'X-Plugin-Token' => $secret_token,
        ),
        'body'      => wp_json_encode($payload),
        'data_format' => 'body',
    );

    $response = wp_remote_post($webhook_url, $args);

    if (is_wp_error($response)) {
        return $response->get_error_message();
    }

    $status_code = wp_remote_retrieve_response_code($response);
    $body = wp_remote_retrieve_body($response);
    $response_data = json_decode($body, true);

    if ($status_code === 202 && isset($response_data['status']) && $response_data['status'] === 'queued') {
        // SUCCESS: Task was queued
        update_post_meta($brief_id, '_acb_status', 'generating');
        if (isset($response_data['task_id'])) {
            update_post_meta($brief_id, '_acb_pa_task_id', sanitize_text_field($response_data['task_id']));
        }
        return true;
    } else {
        // Error from PythonAnywhere
        $error_message = isset($response_data['message']) ? $response_data['message'] : $body;
        return $error_message;
    }
}

add_action('wp_ajax_acb_update_status', 'acb_ajax_update_status_handler');

?>
