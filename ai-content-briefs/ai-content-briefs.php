<?php
/**
 * Plugin Name:       AI Content Briefs & Generator
 * Plugin URI:        https://yourwebsite.com/plugin-info (Optional)
 * Description:       Manages content briefs identified by external analysis and triggers AI content generation.
 * Version:           1.0.0
 * Author:            Your Name
 * Author URI:        https://yourwebsite.com (Optional)
 * License:           GPL v2 or later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       ai-content-briefs
 * Domain Path:       /languages
 */

error_log('🚨 ai-content-briefs.php MAIN FILE LOADED');

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Define Plugin Constants
define( 'ACB_PLUGIN_VERSION', '1.0.0' );
define( 'ACB_PLUGIN_DIR', plugin_dir_path( __FILE__ ) ); // Path to this plugin's directory
define( 'ACB_PLUGIN_URL', plugin_dir_url( __FILE__ ) ); // URL to this plugin's directory
define( 'ACB_POST_TYPE', 'acb_content_brief' );        // Custom Post Type slug
define( 'ACB_SETTINGS_SLUG', 'acb-settings' );        // Settings page slug

/**
 * Ensures required plugin directories exist.
 * Add this function to your main plugin file.
 */
function acb_ensure_directories() {
    $directories = array(
        ACB_PLUGIN_DIR . 'assets/css',
    );

    foreach ($directories as $dir) {
        if (!file_exists($dir)) {
            wp_mkdir_p($dir);
        }
    }
}

/**
 * Plugin Activation Hook
 */
function acb_activate_plugin() {
    // Ensure directories exist
    acb_ensure_directories();
    
    // Ensure CPT is registered on activation
    acb_register_content_brief_cpt();
    // Register meta fields on activation
    acb_register_meta_fields();
    // Flush rewrite rules to ensure CPT permalinks work
    flush_rewrite_rules();
}
register_activation_hook( __FILE__, 'acb_activate_plugin' );

// Also run directory check once when the plugin is updated
add_action('plugins_loaded', function() {
    $stored_version = get_option('acb_plugin_version', '0.0.0');
    if (version_compare(ACB_PLUGIN_VERSION, $stored_version, '>')) {
        acb_ensure_directories();
        update_option('acb_plugin_version', ACB_PLUGIN_VERSION);
    }
});

/**
 * Plugin Deactivation Hook
 */
function acb_deactivate_plugin() {
    // Flush rewrite rules on deactivation
    flush_rewrite_rules();
}
register_deactivation_hook( __FILE__, 'acb_deactivate_plugin' );

// Include necessary files
require_once ACB_PLUGIN_DIR . 'includes/post-types.php';
require_once ACB_PLUGIN_DIR . 'includes/meta-fields.php';
require_once ACB_PLUGIN_DIR . 'includes/admin-pages.php';
require_once ACB_PLUGIN_DIR . 'includes/enqueue.php';
require_once ACB_PLUGIN_DIR . 'includes/ajax-handlers.php';
require_once ACB_PLUGIN_DIR . 'includes/meta-boxes.php';
require_once ACB_PLUGIN_DIR . 'includes/settings.php';
require_once ACB_PLUGIN_DIR . 'includes/rest-api.php';

/**
 * Load plugin textdomain for translation
 */
function acb_load_textdomain() {
    load_plugin_textdomain( 'ai-content-briefs', false, dirname( plugin_basename( __FILE__ ) ) . '/languages' );
}
add_action( 'plugins_loaded', 'acb_load_textdomain' );