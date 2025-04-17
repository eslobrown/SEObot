<?php
/**
 * Registers meta fields for the Content Brief CPT.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Register meta fields for the Content Brief CPT.
 */
function acb_register_meta_fields() {

    $post_type = ACB_POST_TYPE; // Get CPT slug from constant

    // --- Core Brief Data ---
    register_post_meta( $post_type, '_acb_keyword', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Primary keyword for the content brief.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_search_intent', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Identified search intent.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_monthly_searches', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'integer',
        'description'  => __( 'Estimated monthly search volume.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_target_word_count', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'integer',
        'description'  => __( 'Recommended target word count.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_claude_prompt', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'The prompt generated for Claude AI.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );

    // --- !!! ADD MISSING FIELDS HERE !!! ---
    register_post_meta( $post_type, '_acb_current_position', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'number', // Use 'number' for decimals
        'description'  => __( 'Average GSC position.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_content_recommendation', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Content action recommendation (create_new, dual_content).', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_total_impressions', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'integer',
        'description'  => __( 'Total GSC impressions.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_total_clicks', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'integer',
        'description'  => __( 'Total GSC clicks.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_avg_ctr', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'number',
        'description'  => __( 'Average GSC CTR.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_opportunity_score', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'number',
        'description'  => __( 'Calculated opportunity score.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_cpc', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string', // Store as string e.g., "$1.23"
        'description'  => __( 'CPC value.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_competition', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'number',
        'description'  => __( 'Competition score (0-1).', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    // --- !!! END MISSING FIELDS !!! ---

     // --- Analysis Data (Storing as JSON string) ---
     register_post_meta( $post_type, '_acb_analysis_data', array(
        'show_in_rest' => true,
        'single'       => true,
        'type'         => 'string', // Store complex data as a JSON string
        'description'  => __( 'JSON string containing analysis data (opportunity score, phrases, etc.).', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );

    // --- Workflow Status & Tracking ---
    register_post_meta( $post_type, '_acb_status', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string', 'default' => 'pending',
        'description'  => __( 'Workflow status.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_priority', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string', 'default' => '3',
        'description'  => __( 'Priority level.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_notes', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'User notes for this brief.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_pa_task_id', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Task ID from PythonAnywhere.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_error_message', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Error details.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_draft_date', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Date/Time draft created.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
     register_post_meta( $post_type, '_acb_published_date', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'Date/Time post published.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );

    // --- Linking to Generated Content ---
    register_post_meta( $post_type, '_acb_generated_post_id', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'integer',
        'description'  => __( 'ID of the generated WordPress post.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    // --- *** ADD NEW CONTENT URL FIELD *** ---
    register_post_meta( $post_type, '_acb_content_url', array(
        'show_in_rest' => true, // Allow REST API to update this
        'single'       => true,
        'type'         => 'string', // Store URL as a string
        'sanitize_callback' => 'esc_url_raw', // Sanitize as URL
        'description'  => __( 'URL of the associated content post (manually entered or generated).', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    // --- *** END ADD NEW *** ---
     register_post_meta( $post_type, '_acb_generated_post_url', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'URL of the generated WordPress post.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
    register_post_meta( $post_type, '_acb_generated_category_url', array(
        'show_in_rest' => true, 'single' => true, 'type' => 'string',
        'description'  => __( 'URL of the updated category.', 'ai-content-briefs' ),
        'auth_callback' => function() { return current_user_can('edit_posts'); }
    ) );
}
// Register the meta fields on init
add_action( 'init', 'acb_register_meta_fields', 11 ); // Use slightly later priority if needed
?>
