<?php
// /ai-content-briefs/includes/rest-api.php

// Log helper
function acb_log($message) {
    error_log($message, 3, WP_CONTENT_DIR . '/acb-debug.log');
}

// REST API init hook
add_action('rest_api_init', function () {
    acb_log("👋 rest_api_init triggered\n");

    register_rest_route('ai-content-briefs/v1', '/generation-callback', [
        'methods' => 'POST',
        'callback' => 'acb_generation_callback',
        'permission_callback' => '__return_true',
        'args' => [
            'brief_id' => [
                'required' => true,
                'type' => 'integer',
            ],
            'task_id' => [
                'required' => true,
                'type' => 'string',
            ],
            'status' => [
                'required' => true,
                'type' => 'string',
            ],
        ],
    ]);
});

// Callback handler
function acb_generation_callback($request) {
    $brief_id = $request->get_param('brief_id');
    $task_id = $request->get_param('task_id');
    $status = $request->get_param('status'); // 'success' or 'error'
    $generated_content = $request->get_param('generated_content'); // Content from worker (maybe not needed here if saved to post)
    $generated_post_id = $request->get_param('generated_post_id'); // ID of the draft post created
    $featured_image_id = $request->get_param('featured_image_id'); // ID of uploaded image
    $error_message = $request->get_param('error_message');
    $generated_post_url = $request->get_param('generated_post_url'); // <-- Get the URL from payload

    // Basic logging
    acb_log("🎯 acb_generation_callback HIT! Brief ID: $brief_id, Task ID: $task_id, Status: $status\n");
    if ($error_message) {
        acb_log("Error Message: $error_message\n");
    }
    if ($generated_post_id) {
        acb_log("Generated Post ID: $generated_post_id\n");
    }
    if ($generated_post_url) {
         acb_log("Generated Post URL: $generated_post_url\n"); // Log received URL
    }
    if ($featured_image_id) {
         acb_log("Featured Image ID: $featured_image_id\n");
    }

    $post_id = absint($brief_id); // The ID of the Brief CPT post

    if ($status === 'success' && $generated_post_id) {
        // Update brief status
        update_post_meta($post_id, '_acb_status', 'draft_ready');
        update_post_meta($post_id, '_acb_draft_date', current_time('mysql')); // Store draft creation time

        // Store generated post reference
        update_post_meta($post_id, '_acb_generated_post_id', absint($generated_post_id));
        if ($generated_post_url) {
            update_post_meta($post_id, '_acb_content_url', esc_url_raw($generated_post_url)); // <-- SAVE URL
        }
         if ($featured_image_id) {
             // Optionally store the featured image ID on the brief as well, if needed
             update_post_meta($post_id, '_acb_generated_featured_image_id', absint($featured_image_id));
         }
         // Clear any previous error message
        delete_post_meta($post_id, '_acb_error_message');

    } elseif ($status === 'error') {
        // Update status to error and save message
        update_post_meta($post_id, '_acb_status', 'error');
        if ($error_message) {
            update_post_meta($post_id, '_acb_error_message', sanitize_textarea_field($error_message));
        }
    } else {
         // Handle unexpected status or missing post ID on success
         $log_message = "Callback received for Brief ID $brief_id with status '$status'";
         if ($status === 'success' && !$generated_post_id) {
             $log_message .= " but missing generated_post_id.";
             update_post_meta($post_id, '_acb_status', 'error'); // Treat as error if success reported but no ID
             update_post_meta($post_id, '_acb_error_message', 'Callback reported success but post ID was missing.');
         } else {
             $log_message .= " - Unknown status or scenario.";
         }
         acb_log($log_message . "\n");
    }

    // Always update the task ID for reference
    if ($task_id) {
       update_post_meta($post_id, '_acb_pa_task_id', sanitize_text_field($task_id));
    }


    // Return a success response to the Python worker
    return new WP_REST_Response(array(
        'status' => 'success',
        'message' => 'Callback received and brief meta updated.',
        'brief_id' => $post_id,
        'new_status' => get_post_meta($post_id, '_acb_status', true) // Return the status that was actually set
    ), 200);
}
