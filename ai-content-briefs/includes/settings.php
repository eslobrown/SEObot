<?php
/**
 * Handles the Plugin Settings Page.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Add the settings page to the admin menu (under the main CPT menu).
 */
function acb_add_settings_page_menu() {
    add_submenu_page(
        'edit.php?post_type=' . ACB_POST_TYPE,      // Parent slug
        __( 'AI Briefs Settings', 'ai-content-briefs' ), // Page title
        __( 'Settings', 'ai-content-briefs' ),        // Menu title
        'manage_options',                           // Capability
        ACB_SETTINGS_SLUG,                          // Menu slug
        'acb_render_settings_page'                  // Display callback
        // Removed position argument , 15
    );
}
add_action( 'admin_menu', 'acb_add_settings_page_menu' );

/**
 * Register the settings fields using the Settings API.
 */
function acb_register_settings() {
    // Register the main setting group
    register_setting(
        'acb_settings_group', // Option group name (used in settings_fields())
        'acb_settings',       // Option name (where data is stored in wp_options)
        'acb_sanitize_settings' // Sanitization callback function
    );

    // Add settings section
    add_settings_section(
        'acb_section_api', // Section ID
        __( 'API Configuration', 'ai-content-briefs' ), // Section title
        'acb_section_api_callback', // Callback for section description (optional)
        ACB_SETTINGS_SLUG // Page slug where this section appears
    );

    // Add fields to the section
    add_settings_field(
        'acb_webhook_url', // Field ID
        __( 'PythonAnywhere Webhook URL', 'ai-content-briefs' ), // Field title
        'acb_field_webhook_url_render', // Callback to render the field HTML
        ACB_SETTINGS_SLUG, // Page slug
        'acb_section_api' // Section ID where this field belongs
    );

    add_settings_field(
        'acb_secret_token', // Field ID
        __( 'Shared Secret Token', 'ai-content-briefs' ), // Field title
        'acb_field_secret_token_render', // Callback to render the field HTML
        ACB_SETTINGS_SLUG, // Page slug
        'acb_section_api' // Section ID
    );

    // Add field to the API section
    add_settings_field(
        'acb_prompt_generator_url', // Field ID
        __( 'Prompt Generator URL', 'ai-content-briefs' ), // Field title
        'acb_field_prompt_generator_url_render', // Callback to render the field HTML
        ACB_SETTINGS_SLUG, // Page slug
        'acb_section_api' // Section ID
    );

    // Render the prompt generator URL field
    function acb_field_prompt_generator_url_render() {
        $options = get_option( 'acb_settings' );
        $value = isset( $options['acb_prompt_generator_url'] ) ? $options['acb_prompt_generator_url'] : '';
        ?>
        <input type='url' class='regular-text' name='acb_settings[acb_prompt_generator_url]' value='<?php echo esc_url( $value ); ?>' placeholder='https://yourusername.pythonanywhere.com/generate-prompt'>
        <p class="description"><?php esc_html_e( 'The URL of the prompt generator endpoint on your PythonAnywhere app (e.g., /generate-prompt).', 'ai-content-briefs' ); ?></p>
        <?php
    }

     // Add more settings fields/sections here if needed later
}
add_action( 'admin_init', 'acb_register_settings' );

/**
 * Callback function for the API section description (optional).
 */
function acb_section_api_callback() {
    echo '<p>' . esc_html__( 'Configure the connection details for the PythonAnywhere backend service.', 'ai-content-briefs' ) . '</p>';
}

/**
 * Render the Webhook URL field.
 */
function acb_field_webhook_url_render() {
    $options = get_option( 'acb_settings' );
    $value = isset( $options['acb_webhook_url'] ) ? $options['acb_webhook_url'] : '';
    ?>
    <input type='url' class='regular-text' name='acb_settings[acb_webhook_url]' value='<?php echo esc_url( $value ); ?>' placeholder='https://yourusername.pythonanywhere.com/trigger-generation'>
    <p class="description"><?php esc_html_e( 'The URL of the webhook endpoint on your PythonAnywhere app (e.g., /trigger-generation).', 'ai-content-briefs' ); ?></p>
    <?php
}

/**
 * Render the Secret Token field.
 */
function acb_field_secret_token_render() {
    $options = get_option( 'acb_settings' );
    $value = isset( $options['acb_secret_token'] ) ? $options['acb_secret_token'] : '';
    ?>
    <input type='password' class='regular-text' name='acb_settings[acb_secret_token]' value='<?php echo esc_attr( $value ); ?>'>
     <p class="description">
         <?php esc_html_e( 'A strong, unique secret key shared between this plugin and the PythonAnywhere script for security. Must match the WP_PLUGIN_SECRET_TOKEN in the Python .env file.', 'ai-content-briefs' ); ?>
         <br><em><?php esc_html_e( 'Changing this requires updating the PythonAnywhere .env file.', 'ai-content-briefs' ); ?></em>
     </p>
    <?php
}

/**
 * Sanitize the settings options before saving.
 *
 * @param array $input The input array from the settings form.
 * @return array The sanitized array.
 */
function acb_sanitize_settings( $input ) {
    $sanitized_input = array();

    if ( isset( $input['acb_webhook_url'] ) ) {
        $sanitized_input['acb_webhook_url'] = esc_url_raw( trim( $input['acb_webhook_url'] ) );
    }
    if ( isset( $input['acb_secret_token'] ) ) {
        // Only update token if a new value is provided, otherwise keep the old one
        if ( ! empty($input['acb_secret_token']) && strpos($input['acb_secret_token'], '*') === false ) {
            $sanitized_input['acb_secret_token'] = sanitize_text_field( trim( $input['acb_secret_token'] ) );
        } else {
            $options = get_option( 'acb_settings' );
            $sanitized_input['acb_secret_token'] = isset( $options['acb_secret_token'] ) ? $options['acb_secret_token'] : '';
        }
    }
    // Add this block to handle the prompt generator URL
    if ( isset( $input['acb_prompt_generator_url'] ) ) {
        $sanitized_input['acb_prompt_generator_url'] = esc_url_raw( trim( $input['acb_prompt_generator_url'] ) );
    }

    return $sanitized_input;
}

/**
 * Render the main settings page HTML structure.
 */
function acb_render_settings_page() {
    // Check user capabilities
    if ( ! current_user_can( 'manage_options' ) ) {
        return;
    }

    // Show confirmation messages (settings saved, etc.)
    settings_errors( 'acb_settings_messages' );
    ?>
    <div class="wrap">
        <h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
        <form action="options.php" method="post">
            <?php
            // Output security fields for the registered setting group
            settings_fields( 'acb_settings_group' );
            // Output the sections and fields for the specified page slug
            do_settings_sections( ACB_SETTINGS_SLUG );
            // Output save settings button
            submit_button( __( 'Save Settings', 'ai-content-briefs' ) );
            ?>
        </form>
    </div>
    <?php
}

?>