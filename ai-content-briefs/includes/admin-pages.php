<?php
/**
 * Handles the admin page display for Content Briefs.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Include the List Table class
require_once ACB_PLUGIN_DIR . 'includes/class-acb-briefs-list-table.php';

/**
 * Callback function to display the list table page content.
 */
function acb_display_briefs_list_page() {
    // Create an instance of our package class...
    $briefs_list_table = new ACB_Briefs_List_Table();
    // Fetch, prepare, sort, and filter our data...
    $briefs_list_table->prepare_items();
    ?>
    <div class="wrap">
        <h1 class="wp-heading-inline"><?php echo esc_html( get_admin_page_title() ); ?></h1>
        <hr class="wp-header-end">
        <!-- Views -->
        <?php $briefs_list_table->views(); ?>
        <br class="clear">
        <!-- Search Box -->
         <form method="get">
            <input type="hidden" name="page" value="<?php echo esc_attr($_REQUEST['page']); ?>" />
            <input type="hidden" name="post_type" value="<?php echo esc_attr(ACB_POST_TYPE); ?>" />
            <?php if (isset($_REQUEST['post_status'])): ?>
                <input type="hidden" name="post_status" value="<?php echo esc_attr($_REQUEST['post_status']); ?>" />
            <?php endif; ?>
            <?php $briefs_list_table->search_box('Search Briefs', 'acb-search-input'); ?>
        </form>
        <!-- Display the table -->
        <form method="post">
            <input type="hidden" name="page" value="<?php echo esc_attr($_REQUEST['page']); ?>" />
            <?php $briefs_list_table->display(); ?>
        </form>
    </div>
    <?php
}

/**
 * Filter the columns displayed on the CPT list table screen.
 *
 * @param array $columns Existing columns.
 * @return array Modified columns.
 */
function acb_set_custom_edit_columns( $columns ) {
    // We instantiate our list table class just to easily get the columns *it* defines.
    $list_table = new ACB_Briefs_List_Table();
    return $list_table->get_columns(); // Return the columns defined in your class
}
// Filter hook is manage_edit-{POST_TYPE}_columns
add_filter( 'manage_edit-' . ACB_POST_TYPE . '_columns', 'acb_set_custom_edit_columns' );

/**
 * Render content for custom columns on the CPT list table screen.
 *
 * @param string $column_name The name of the column to display.
 * @param int    $post_id     The current post ID.
 */
function acb_custom_column_content( $column_name, $post_id ) {
    // Skip known columns that WordPress handles automatically
    if ( $column_name === 'cb' || $column_name === 'date' ) {
        return;
    }
    
    // Handle title column separately if needed
    if ( $column_name === 'title' ) {
        // WordPress usually handles this automatically
        return;
    }
    
    // Get all required meta data at once
    $status = get_post_meta( $post_id, '_acb_status', true ) ?: 'pending';
    $priority = get_post_meta( $post_id, '_acb_priority', true ) ?: '3';
    $avg_position = get_post_meta( $post_id, '_acb_current_position', true );
    $content_recommendation = get_post_meta( $post_id, '_acb_content_recommendation', true );
    $opportunity_score = get_post_meta( $post_id, '_acb_opportunity_score', true );
    $intent = get_post_meta( $post_id, '_acb_search_intent', true );
    $volume = get_post_meta( $post_id, '_acb_monthly_searches', true );
    $target_wc = get_post_meta( $post_id, '_acb_target_word_count', true );
    $content_url = get_post_meta( $post_id, '_acb_content_url', true );
    
    // Render content based on column name
    switch ( $column_name ) {
        case 'status':
            $status_options = array(
                'pending'     => __( 'Pending', 'ai-content-briefs' ),
                'approved'    => __( 'Approved', 'ai-content-briefs' ),
                'generating'  => __( 'Generating', 'ai-content-briefs' ),
                'draft_ready' => __( 'Draft Ready', 'ai-content-briefs' ),
                'published'   => __( 'Published', 'ai-content-briefs' ),
                'error'       => __( 'Error', 'ai-content-briefs' ),
                'skip'        => __( 'Skip', 'ai-content-briefs' ),
            );
            
            // Create nonce for AJAX security
            $nonce = wp_create_nonce('acb_update_status_' . $post_id);
            
            // Output the dropdown with data attributes for AJAX
            echo '<select name="acb_status_' . esc_attr($post_id) . '" 
                   class="acb-status-select" 
                   data-brief-id="' . esc_attr($post_id) . '" 
                   data-nonce="' . esc_attr($nonce) . '" 
                   data-current-status="' . esc_attr($status) . '"';
            
            // Disable dropdown if status is 'generating'
            if ($status === 'generating') {
                echo ' disabled="disabled"';
            }
            
            echo '>';
            
            // Add options with proper classes based on status value
            foreach ($status_options as $value => $label) {
                // Disable the generating option unless it's the current status
                $option_disabled = ($value === 'generating' && $status !== 'generating') ? ' disabled' : '';
                $selected = selected($status, $value, false);
                echo '<option value="' . esc_attr($value) . '" class="status-' . esc_attr($value) . '"' . $selected . $option_disabled . '>' . 
                     esc_html($label) . '</option>';
            }
            
            echo '</select>';
            echo '<span class="spinner" style="float: none; vertical-align: middle; margin-left: 5px; visibility: hidden;"></span>';
            break;
            
        case 'priority':
            $priority_map = array(
                '1' => '1 (High)',
                '2' => '2',
                '3' => '3 (Medium)',
                '4' => '4',
                '5' => '5 (Low)'
            );
            echo isset($priority_map[$priority]) ? esc_html($priority_map[$priority]) : esc_html($priority);
            break;
            
        case 'avg_position':
            echo is_numeric($avg_position) ? number_format_i18n((float)$avg_position, 2) : 'N/A';
            break;
            
        case 'recommendation':
            echo esc_html(ucwords(str_replace('_', ' ', $content_recommendation ?: 'N/A')));
            break;
            
        case 'opportunity_score':
            echo is_numeric($opportunity_score) ? number_format_i18n((float)$opportunity_score, 1) : 'N/A';
            break;
            
        case 'intent':
            echo esc_html($intent ?: 'N/A');
            break;
            
        case 'volume':
            echo is_numeric($volume) ? number_format_i18n((int)$volume) : 'N/A';
            break;
            
        case 'target_wc':
            echo is_numeric($target_wc) ? number_format_i18n((int)$target_wc) : 'N/A';
            break;
            
        case 'content_url':
            if ($content_url) {
                echo '<a href="' . esc_url($content_url) . '" target="_blank" title="' . esc_attr($content_url) . '">' . 
                    esc_html(wp_basename(untrailingslashit($content_url)) ?: substr($content_url, 0, 30).'...') . '</a>';
            } else {
                echo '—';
            }
            break;
            
        default:
            // Fallback for any other columns
            $meta_value = get_post_meta($post_id, '_acb_' . $column_name, true);
            if ($meta_value) {
                echo esc_html($meta_value);
            } else {
                echo '—';
            }
            break;
    }
}

// Action hook is manage_{POST_TYPE}_posts_custom_column
add_action( 'manage_' . ACB_POST_TYPE . '_posts_custom_column' , 'acb_custom_column_content', 10, 2 );

/**
 * Register sortable columns.
 *
 * @param array $columns Existing sortable columns.
 * @return array Modified sortable columns.
 */
function acb_set_sortable_columns( $columns ) {
    $list_table = new ACB_Briefs_List_Table();
    return $list_table->get_sortable_columns(); // Return sortable columns from your class
}
// Filter hook is manage_edit-{POST_TYPE}_sortable_columns
add_filter( 'manage_edit-' . ACB_POST_TYPE . '_sortable_columns', 'acb_set_sortable_columns' );

/**
 * Handle sorting logic for custom meta columns.
 *
 * @param WP_Query $query The main query object.
 */
function acb_handle_custom_column_sorting( $query ) {
    // Only modify the main query on the admin screen for our CPT
    if ( ! is_admin() || ! $query->is_main_query() || $query->get('post_type') !== ACB_POST_TYPE ) {
        return;
    }

    $orderby = $query->get('orderby');
    $order   = $query->get('order'); // No need to sanitize here, WP_Query does it

    if ( empty($orderby) ) return; // No sorting requested

    $list_table = new ACB_Briefs_List_Table();
    $sortable_columns = $list_table->get_sortable_columns();

    // Check if the requested orderby is one of our sortable columns
    if ( array_key_exists( $orderby, $sortable_columns ) ) {
        $meta_key_map = [
             'status'            => '_acb_status',
             'priority'          => '_acb_priority',
             'opportunity_score' => '_acb_opportunity_score',
             'avg_position'      => '_acb_current_position',
             'volume'            => '_acb_monthly_searches',
             'target_wc'         => '_acb_target_word_count',
        ];

        if (isset($meta_key_map[$orderby])) {
            $query->set('meta_key', $meta_key_map[$orderby]);
             // Ensure numeric sorting for appropriate fields
             if (in_array($orderby, ['priority', 'opportunity_score', 'avg_position', 'volume', 'target_wc'])) {
                 $query->set('orderby', 'meta_value_num');
             } else {
                 $query->set('orderby', 'meta_value');
             }
             // Order is already set by WP_Query based on URL parameters
        }
        // Note: 'title' and 'date' sorting are handled natively by WP_Query when 'orderby' is set
    }
}
add_action( 'pre_get_posts', 'acb_handle_custom_column_sorting' );

/**
 * Handle empty trash action
 */
function acb_handle_empty_trash() {
    if (isset($_REQUEST['action']) && $_REQUEST['action'] === 'empty_trash' &&
        isset($_REQUEST['_wpnonce']) && wp_verify_nonce($_REQUEST['_wpnonce'], 'empty-trash-' . ACB_POST_TYPE)) {
        
        global $wpdb;
        
        // Get all trashed briefs
        $trashed_briefs = $wpdb->get_col(
            $wpdb->prepare(
                "SELECT ID FROM $wpdb->posts WHERE post_type = %s AND post_status = 'trash'",
                ACB_POST_TYPE
            )
        );
        
        // Delete them permanently
        foreach ($trashed_briefs as $brief_id) {
            wp_delete_post($brief_id, true);
        }
        
        // Redirect back
        wp_redirect(admin_url("edit.php?post_type=" . ACB_POST_TYPE . "&post_status=trash&trashed=1"));
        exit();
    }
}
add_action('admin_init', 'acb_handle_empty_trash');

/**
 * Add admin notices for trash actions
 */
function acb_admin_notices() {
    $screen = get_current_screen();
    
    // Only on our post type screen
    if ($screen->post_type !== ACB_POST_TYPE) {
        return;
    }
    
    if (isset($_GET['trashed']) && $_GET['trashed'] > 0) {
        $count = absint($_GET['trashed']);
        $message = sprintf(_n('%s brief moved to the Trash.', '%s briefs moved to the Trash.', $count, 'ai-content-briefs'), number_format_i18n($count));
        echo '<div class="notice notice-success is-dismissible"><p>' . $message . '</p></div>';
    }
    
    if (isset($_GET['untrashed']) && $_GET['untrashed'] > 0) {
        $count = absint($_GET['untrashed']);
        $message = sprintf(_n('%s brief restored from the Trash.', '%s briefs restored from the Trash.', $count, 'ai-content-briefs'), number_format_i18n($count));
        echo '<div class="notice notice-success is-dismissible"><p>' . $message . '</p></div>';
    }
    
    if (isset($_GET['deleted']) && $_GET['deleted'] > 0) {
        $count = absint($_GET['deleted']);
        $message = sprintf(_n('%s brief permanently deleted.', '%s briefs permanently deleted.', $count, 'ai-content-briefs'), number_format_i18n($count));
        echo '<div class="notice notice-success is-dismissible"><p>' . $message . '</p></div>';
    }
}
add_action('admin_notices', 'acb_admin_notices');

/**
 * Add row actions for trash/restore/delete
 */
function acb_row_actions($actions, $post) {
    if ($post->post_type !== ACB_POST_TYPE) {
        return $actions;
    }
    
    // For trashed posts
    if ($post->post_status === 'trash') {
        // Remove edit link
        unset($actions['edit']);
        
        // Add restore link
        $actions['untrash'] = sprintf(
            '<a href="%s" aria-label="%s">%s</a>',
            wp_nonce_url(admin_url(sprintf('post.php?post=%d&action=untrash', $post->ID)), 'untrash-post_' . $post->ID),
            esc_attr(sprintf(__('Restore &#8220;%s&#8221; from the Trash', 'ai-content-briefs'), get_the_title($post->ID))),
            __('Restore', 'ai-content-briefs')
        );
        
        // Add delete permanently link
        $actions['delete'] = sprintf(
            '<a href="%s" class="submitdelete" aria-label="%s">%s</a>',
            wp_nonce_url(admin_url(sprintf('post.php?post=%d&action=delete', $post->ID)), 'delete-post_' . $post->ID),
            esc_attr(sprintf(__('Delete &#8220;%s&#8221; permanently', 'ai-content-briefs'), get_the_title($post->ID))),
            __('Delete Permanently', 'ai-content-briefs')
        );
    } 
    // For non-trashed posts
    else {
        // Add trash link
        $actions['trash'] = sprintf(
            '<a href="%s" class="submitdelete" aria-label="%s">%s</a>',
            wp_nonce_url(admin_url(sprintf('post.php?post=%d&action=trash', $post->ID)), 'trash-post_' . $post->ID),
            esc_attr(sprintf(__('Move &#8220;%s&#8221; to the Trash', 'ai-content-briefs'), get_the_title($post->ID))),
            __('Trash', 'ai-content-briefs')
        );
    }
    
    return $actions;
}
add_filter('post_row_actions', 'acb_row_actions', 10, 2);