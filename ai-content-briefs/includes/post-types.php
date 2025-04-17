<?php
/**
 * Registers the Content Brief Custom Post Type.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Register the Content Brief CPT.
 */
function acb_register_content_brief_cpt() {

    $labels = array(
        'name'                  => _x( 'Content Briefs', 'Post type general name', 'ai-content-briefs' ),
        'singular_name'         => _x( 'Content Brief', 'Post type singular name', 'ai-content-briefs' ),
        'menu_name'             => _x( 'AI Content Briefs', 'Admin Menu text', 'ai-content-briefs' ),
        'name_admin_bar'        => _x( 'Content Brief', 'Add New on Toolbar', 'ai-content-briefs' ),
        'add_new'               => __( 'Add New Brief', 'ai-content-briefs' ),
        'add_new_item'          => __( 'Add New Brief', 'ai-content-briefs' ),
        'new_item'              => __( 'New Content Brief', 'ai-content-briefs' ),
        'edit_item'             => __( 'Edit Content Brief', 'ai-content-briefs' ),
        'view_item'             => __( 'View Content Brief', 'ai-content-briefs' ),
        // --- CHANGE THIS LINE ---
        'all_items'             => __( 'All Briefs', 'ai-content-briefs' ), // Use this label for the "All" page
        // --- END CHANGE ---
        'search_items'          => __( 'Search Content Briefs', 'ai-content-briefs' ),
        'parent_item_colon'     => __( 'Parent Content Briefs:', 'ai-content-briefs' ),
        'not_found'             => __( 'No Content Briefs found.', 'ai-content-briefs' ),
        'not_found_in_trash'    => __( 'No Content Briefs found in Trash.', 'ai-content-briefs' ),
        'featured_image'        => _x( 'Content Brief Cover Image', 'Overrides the “Featured Image” phrase for this post type. Added in 4.3', 'ai-content-briefs' ),
        'set_featured_image'    => _x( 'Set cover image', 'Overrides the “Set featured image” phrase for this post type. Added in 4.3', 'ai-content-briefs' ),
        'remove_featured_image' => _x( 'Remove cover image', 'Overrides the “Remove featured image” phrase for this post type. Added in 4.3', 'ai-content-briefs' ),
        'use_featured_image'    => _x( 'Use as cover image', 'Overrides the “Use as featured image” phrase for this post type. Added in 4.3', 'ai-content-briefs' ),
        'archives'              => _x( 'Content Brief archives', 'The post type archive label used in nav menus. Default “Post Archives”. Added in 4.4', 'ai-content-briefs' ),
        'insert_into_item'      => _x( 'Insert into Content Brief', 'Overrides the “Insert into post”/”Insert into page” phrase (used when inserting media into a post). Added in 4.4', 'ai-content-briefs' ),
        'uploaded_to_this_item' => _x( 'Uploaded to this Content Brief', 'Overrides the “Uploaded to this post”/”Uploaded to this page” phrase (used when viewing media attached to a post). Added in 4.4', 'ai-content-briefs' ),
        'filter_items_list'     => _x( 'Filter Content Briefs list', 'Screen reader text for the filter links heading on the post type listing screen. Default “Filter posts list”/”Filter pages list”. Added in 4.4', 'ai-content-briefs' ),
        'items_list_navigation' => _x( 'Content Briefs list navigation', 'Screen reader text for the pagination heading on the post type listing screen. Default “Posts list navigation”/”Pages list navigation”. Added in 4.4', 'ai-content-briefs' ),
        'items_list'            => _x( 'Content Briefs list', 'Screen reader text for the items list heading on the post type listing screen. Default “Posts list”/”Pages list”. Added in 4.4', 'ai-content-briefs' ),
    );

    $args = array(
        'labels'             => $labels,
        'public'             => false,
        'publicly_queryable' => false,
        'show_ui'            => true,
        'show_in_menu'       => true,
        'query_var'          => false,
        'rewrite'            => false,
        'capability_type'    => 'post',
        'has_archive'        => false,
        'hierarchical'       => false,
        'menu_position'      => 25,
        'menu_icon'          => 'dashicons-clipboard',
        'supports'           => array( 'title', 'custom-fields' ),
        'show_in_rest'       => true,
        'rest_base'          => 'content-briefs',
        'rest_controller_class' => 'WP_REST_Posts_Controller',
    );

    register_post_type( ACB_POST_TYPE, $args );
}
add_action( 'init', 'acb_register_content_brief_cpt' );

/**
 * Modify CPT messages (optional, for better user feedback)
 */
function acb_updated_messages( $messages ) {
    global $post;

    $messages[ACB_POST_TYPE] = array(
        0 => '', // Unused. Messages start at index 1.
        1 => __( 'Content Brief updated.', 'ai-content-briefs' ),
        2 => __( 'Custom field updated.', 'ai-content-briefs' ),
        3 => __( 'Custom field deleted.', 'ai-content-briefs' ),
        4 => __( 'Content Brief updated.', 'ai-content-briefs' ),
        /* translators: %s: date and time of the revision */
        5 => isset( $_GET['revision'] ) ? sprintf( __( 'Content Brief restored to revision from %s', 'ai-content-briefs' ), wp_post_revision_title( (int) $_GET['revision'], false ) ) : false,
        6 => __( 'Content Brief published.', 'ai-content-briefs' ),
        7 => __( 'Content Brief saved.', 'ai-content-briefs' ),
        8 => __( 'Content Brief submitted.', 'ai-content-briefs' ),
        9 => sprintf(
            __( 'Content Brief scheduled for: <strong>%1$s</strong>.', 'ai-content-briefs' ),
            // translators: Publish box date format, see http://php.net/date
            date_i18n( __( 'M j, Y @ G:i', 'ai-content-briefs' ), strtotime( $post->post_date ) )
        ),
        10 => __( 'Content Brief draft updated.', 'ai-content-briefs' ),
    );

    return $messages;
}
add_filter( 'post_updated_messages', 'acb_updated_messages' );

?>