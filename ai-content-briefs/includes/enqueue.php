<?php
/**
 * Enqueues admin scripts and styles.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Enqueue admin scripts and styles specifically for the ACB list table page.
 *
 * @param string $hook_suffix The current admin page hook suffix.
 */
function acb_enqueue_admin_scripts( $hook_suffix ) {
    global $pagenow;
    $current_screen = get_current_screen();

    // --- Log Screen Info Unconditionally using error_log ---
    if ($current_screen) {
         $screen_info_message = sprintf(
             '[ACB Debug] Enqueue Hook Fired: Hook=%s | Screen ID=%s | Screen Base=%s | Screen Post Type=%s | $pagenow=%s',
             esc_html($hook_suffix),
             esc_html(isset($current_screen->id) ? $current_screen->id : 'N/A'),
             esc_html(isset($current_screen->base) ? $current_screen->base : 'N/A'),
             esc_html(isset($current_screen->post_type) ? $current_screen->post_type : 'N/A'),
             esc_html($pagenow)
         );
         error_log($screen_info_message);
    } else {
         error_log('[ACB Debug] Enqueue Hook Fired: get_current_screen() returned null.');
    }
    // --- End Unconditional Log ---


    // --- Improved Conditional Check for Enqueuing ---
    // Check if we're on the right screen for our custom post type
    if ($current_screen && $current_screen->post_type === ACB_POST_TYPE) {
        error_log('[ACB Debug] Enqueue Condition Met: Post type matches ' . ACB_POST_TYPE);
        
        // Check if script file exists
        $script_path = ACB_PLUGIN_DIR . 'assets/js/admin-briefs.js';
        if (file_exists($script_path)) {
             error_log('[ACB Debug] Script file check: EXISTS at ' . $script_path);
        } else {
             error_log('[ACB Error] Script file check: *** DOES NOT EXIST *** at ' . $script_path);
        }
        
        // Check if CSS file exists
        $css_path = ACB_PLUGIN_DIR . 'assets/css/admin-briefs.css';
        if (file_exists($css_path)) {
             error_log('[ACB Debug] CSS file check: EXISTS at ' . $css_path);
        } else {
             error_log('[ACB Error] CSS file check: *** DOES NOT EXIST *** at ' . $css_path);
        }
        
        // Enqueue the CSS file
        wp_enqueue_style(
            'acb-admin-styles',
            ACB_PLUGIN_URL . 'assets/css/admin-briefs.css',
            array(),
            ACB_PLUGIN_VERSION
        );
        
        // Enqueue the script
        wp_enqueue_script(
            'acb-admin-script',
            ACB_PLUGIN_URL . 'assets/js/admin-briefs.js',
            array( 'jquery' ),
            ACB_PLUGIN_VERSION,
            true
        );

        // Localize the script with data
        wp_localize_script(
            'acb-admin-script',
            'acb_ajax_object',
            array(
                'ajax_url' => admin_url( 'admin-ajax.php' ),
                'error_message' => __('An error occurred. Please try again.', 'ai-content-briefs'),
            )
        );
        
        error_log('[ACB Debug] Successfully enqueued style, script, and localized data.');
    } else {
        // --- Log if condition failed ---
        if ($current_screen) {
            $reason_details = sprintf(
                'Current screen post_type is "%s" (needed "%s").',
                esc_html($current_screen->post_type ?? 'none'),
                esc_html(ACB_POST_TYPE)
            );
        } else {
            $reason_details = 'current_screen is null.';
        }
        error_log('[ACB Debug] Enqueue Condition Failed (Post Type Check). Details: ' . $reason_details);
        // --- End Log ---
    }
}
add_action( 'admin_enqueue_scripts', 'acb_enqueue_admin_scripts' );

?>