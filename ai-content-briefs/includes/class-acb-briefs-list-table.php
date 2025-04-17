<?php
/**
 * Creates the WP_List_Table class for Content Briefs.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Load WP_List_Table if not already loaded
if ( ! class_exists( 'WP_List_Table' ) ) {
    require_once ABSPATH . 'wp-admin/includes/class-wp-list-table.php';
}

class ACB_Briefs_List_Table extends WP_List_Table {

    /**
     * Status options for display and dropdown.
     */
    private $status_options = array(); // <-- ADDED PROPERTY

    /**
     * Constructor.
     */
    public function __construct() {
        parent::__construct( array(
            'singular' => __( 'Content Brief', 'ai-content-briefs' ), // <-- USE __() FOR TRANSLATION
            'plural'   => __( 'Content Briefs', 'ai-content-briefs' ), // <-- USE __() FOR TRANSLATION
            'ajax'     => false // Does this table support ajax?
        ) );

        // --- ADDED: Initialize status options ---
        $this->status_options = array(
            'pending'     => __( 'Pending', 'ai-content-briefs' ),
            'approved'    => __( 'Approved', 'ai-content-briefs' ),
            'generating'  => __( 'Generating', 'ai-content-briefs' ),
            'draft_ready' => __( 'Draft Ready', 'ai-content-briefs' ),
            'published'   => __( 'Published', 'ai-content-briefs' ),
            'error'       => __( 'Error', 'ai-content-briefs' ),
            'skip'        => __( 'Skip', 'ai-content-briefs' ), // <-- ADDED
        );
        // --- END ADDED ---
    }

    // --- Keep existing get_views() method ---
    /**
     * Get views to display (All, Published, Trash)
     * @return array
     */
    public function get_views() {
        global $wpdb;
        
        $status_links = array();
        $post_type = ACB_POST_TYPE;
        
        // Count posts in each status
        $counts = $wpdb->get_results(
            $wpdb->prepare(
                "SELECT post_status, COUNT(*) AS num_posts FROM {$wpdb->posts} 
                WHERE post_type = %s 
                GROUP BY post_status",
                $post_type
            ),
            ARRAY_A
        );
        
        $count_map = array();
        foreach ($counts as $row) {
            $count_map[$row['post_status']] = $row['num_posts'];
        }
        
        // Total count
        $total_posts = array_sum($count_map);
        
        // All link
        $class = (empty($_REQUEST['post_status']) || $_REQUEST['post_status'] == 'all') ? ' class="current"' : '';
        $status_links['all'] = sprintf(
            '<a href="%s"%s>%s <span class="count">(%s)</span></a>',
            admin_url("edit.php?post_type={$post_type}"),
            $class,
            __('All', 'ai-content-briefs'),
            number_format_i18n($total_posts)
        );
        
        // Published link
        $count = isset($count_map['publish']) ? $count_map['publish'] : 0;
        $class = (!empty($_REQUEST['post_status']) && $_REQUEST['post_status'] == 'publish') ? ' class="current"' : '';
        $status_links['publish'] = sprintf(
            '<a href="%s"%s>%s <span class="count">(%s)</span></a>',
            admin_url("edit.php?post_type={$post_type}&post_status=publish"),
            $class,
            __('Published', 'ai-content-briefs'),
            number_format_i18n($count)
        );
        
        // Trash link
        $count = isset($count_map['trash']) ? $count_map['trash'] : 0;
        $class = (!empty($_REQUEST['post_status']) && $_REQUEST['post_status'] == 'trash') ? ' class="current"' : '';
        $status_links['trash'] = sprintf(
            '<a href="%s"%s>%s <span class="count">(%s)</span></a>',
            admin_url("edit.php?post_type={$post_type}&post_status=trash"),
            $class,
            __('Trash', 'ai-content-briefs'),
            number_format_i18n($count)
        );
        
        return $status_links;
    }


    /**
     * Get columns to show in the list table.
     *
     * @return array
     */
    public function get_columns() {
        return array(
            'cb'                       => '<input type="checkbox" />',
            'title'                    => __( 'Keyword (Brief Title)', 'ai-content-briefs' ),
            'status'                   => __( 'Status', 'ai-content-briefs' ),
            'priority'                 => __( 'Priority', 'ai-content-briefs' ),
            'avg_position'             => __( 'Avg. Pos.', 'ai-content-briefs' ),
            'content_recommendation'   => __( 'Recommendation', 'ai-content-briefs' ),
            'opportunity_score'        => __( 'Opp. Score', 'ai-content-briefs' ),
            'intent'                   => __( 'Intent', 'ai-content-briefs' ),
            'volume'                   => __( 'Volume', 'ai-content-briefs' ),
            'target_wc'                => __( 'Target WC', 'ai-content-briefs' ),
            'content_url'              => __( 'Content URL', 'ai-content-briefs' ), // <-- ADDED COLUMN
            'date'                     => __( 'Date Created', 'ai-content-briefs' )
        );
    }

    /**
     * Get sortable columns.
     *
     * @return array
     */
    public function get_sortable_columns() {
        // Add sorting if desired, maybe by date implicitly associated with URL? Less direct.
        return array(
            'title'             => array( 'title', true ),
            'status'            => array( 'status', false ),
            'priority'          => array( 'priority', false ),
            'avg_position'      => array( 'avg_position', false ),
            'opportunity_score' => array( 'opportunity_score', false ),
            'volume'            => array( 'volume', false ),
            'target_wc'         => array( 'target_wc', false ),
            'date'              => array( 'date', true )
        );
    }

     /**
      * Get the total number of items. Used for pagination.
      */
     private function get_briefs_count() {
         // Simplified count using WP core function
         $counts = wp_count_posts( ACB_POST_TYPE );
         $total = 0;
         // Sum up relevant statuses depending on current view
         $current_status = isset($_REQUEST['post_status']) ? $_REQUEST['post_status'] : 'all';
         if ($current_status === 'all') {
            // Sum all except trash and auto-draft
             foreach (get_post_stati(['show_in_admin_all_list' => true]) as $status) {
                 $total += $counts->$status ?? 0;
             }
         } elseif (isset($counts->$current_status)) {
            $total = $counts->$current_status;
         }
         return $total;
     }


    /**
     * Get the briefs data for the current view.
     *
     * @param int $per_page
     * @param int $current_page
     * @return array
     */
    private function get_briefs_data( $per_page, $current_page = 1 ) {
        $briefs_data = array();
        $args = array(
            'post_type'      => ACB_POST_TYPE,
            'posts_per_page' => $per_page,
            'paged'          => $current_page,
            'post_status'    => 'any',
            'orderby'        => 'date', // Default orderby
            'order'          => 'DESC'  // Default order
        );

        // --- Status Filtering (Adjusted) ---
        $current_view_status = isset($_REQUEST['post_status']) ? sanitize_key($_REQUEST['post_status']) : 'all';
        if ($current_view_status !== 'all') {
            $args['post_status'] = $current_view_status;
        } else {
            // 'all' view should exclude trash
             $args['post_status'] = array_diff(get_post_stati(), ['trash', 'auto-draft']);
        }
        // --- End Status Filtering ---


        // --- Sorting Logic (Combined from both versions) ---
        $orderby = isset( $_REQUEST['orderby'] ) ? sanitize_key( $_REQUEST['orderby'] ) : 'date';
        $order   = isset( $_REQUEST['order'] ) ? strtoupper( sanitize_key( $_REQUEST['order'] ) ) : 'DESC';
        $sortable_columns = $this->get_sortable_columns();

        if ( array_key_exists( $orderby, $sortable_columns ) ) {
            $orderby_value = $sortable_columns[$orderby][0];
             $meta_key_map = [ // Make sure this map includes all sortable meta keys
                 'status'            => '_acb_status',
                 'priority'          => '_acb_priority',
                 'opportunity_score' => '_acb_opportunity_score',
                 'avg_position'      => '_acb_current_position',
                 'volume'            => '_acb_monthly_searches', // Map volume to meta key
                 'target_wc'         => '_acb_target_word_count', // Map target_wc to meta key
             ];

             if (isset($meta_key_map[$orderby_value])) {
                 $args['meta_key'] = $meta_key_map[$orderby_value];
                  // Ensure numeric sorting for appropriate fields
                 if (in_array($orderby_value, ['priority', 'opportunity_score', 'avg_position', 'volume', 'target_wc', 'avg_comp_urds'])) {
                     $args['orderby'] = 'meta_value_num';
                 } else {
                     $args['orderby'] = 'meta_value';
                 }
             } elseif (in_array($orderby_value, ['title', 'date'])) {
                  $args['orderby'] = $orderby_value;
             } else {
                 $args['orderby'] = 'date'; // Default
             }
             $args['order'] = $order;
        }
        // --- End Sorting Logic ---

        // Add search query
        if (!empty($_REQUEST['s'])) {
            $args['s'] = sanitize_text_field($_REQUEST['s']);
        }

        $query = new WP_Query( $args );
        $briefs_data = array();

        if ( $query->have_posts() ) {
            while ( $query->have_posts() ) {
                $query->the_post();
                $post_id = get_the_ID();
                $briefs_data[] = array(
                    'ID'                       => $post_id,
                    'title'                    => get_the_title(),
                    'keyword'                  => get_post_meta( $post_id, '_acb_keyword', true ) ?: get_the_title(),
                    'status'                   => get_post_meta( $post_id, '_acb_status', true ) ?: 'pending',
                    'priority'                 => get_post_meta( $post_id, '_acb_priority', true ) ?: '3',
                    'intent'                   => get_post_meta( $post_id, '_acb_search_intent', true ),
                    'volume'                   => get_post_meta( $post_id, '_acb_monthly_searches', true ),
                    'target_wc'                => get_post_meta( $post_id, '_acb_target_word_count', true ),
                    'opportunity_score'        => get_post_meta( $post_id, '_acb_opportunity_score', true ),
                    'avg_position'             => get_post_meta( $post_id, '_acb_current_position', true ),
                    'content_recommendation'   => get_post_meta( $post_id, '_acb_content_recommendation', true ),
                    'generated_post_id'        => get_post_meta( $post_id, '_acb_generated_post_id', true ),
                    'post_status'              => get_post_status($post_id),
                    'content_url'              => get_post_meta( $post_id, '_acb_content_url', true ), // <-- FETCH META
                    'date'                     => get_the_date()
                );
                // --- END FETCH ---
            }
            wp_reset_postdata();
        }

        return $briefs_data;
    }

    /**
     * Prepare the items for the table to process.
     * Merged prepare_items logic
     */
    public function prepare_items() {
        $columns  = $this->get_columns();
        $hidden   = $this->get_hidden_columns();
        $sortable = $this->get_sortable_columns();
        $this->_column_headers = array( $columns, $hidden, $sortable, 'title' ); // Added primary column

        // Handle bulk actions
        $this->process_bulk_action(); // Use the merged/new bulk action handler

        // Pagination parameters
        $per_page     = $this->get_items_per_page( 'acb_briefs_per_page', 20 ); // Make per_page filterable
        $current_page = $this->get_pagenum();
        $total_items  = $this->get_briefs_count(); // Use combined count logic

        $this->set_pagination_args( array(
            'total_items' => $total_items,
            'per_page'    => $per_page,
            'total_pages' => ceil($total_items / $per_page) // Calculate total pages
        ) );

        // Fetch the data using the combined logic
        $this->items = $this->get_briefs_data( $per_page, $current_page );
    }

    // --- Keep existing get_hidden_columns() ---
    public function get_hidden_columns(){ return array(); }

    // --- MERGED get_bulk_actions() ---
    public function get_bulk_actions() {
        $actions = array();
        $current_status = isset( $_REQUEST['post_status'] ) ? $_REQUEST['post_status'] : '';

        if ( $current_status === 'trash' ) {
            $actions['untrash'] = __( 'Restore', 'ai-content-briefs' );
            $actions['delete_permanently'] = __( 'Delete Permanently', 'ai-content-briefs' );
        } else {
            // Combine actions from both versions
            $actions['approve'] = __( 'Approve Selected', 'ai-content-briefs' );
            // $actions['bulk_generate']  = __( 'Generate for Approved', 'ai-content-briefs' ); // Keep commented for now
            $actions['trash'] = __( 'Move to Trash', 'ai-content-briefs' );
        }
        return $actions;
    }
    // --- END MERGED get_bulk_actions() ---


    // --- MERGED process_bulk_action() ---
    public function process_bulk_action() {
        $action = $this->current_action();
        $nonce = isset( $_REQUEST['_wpnonce'] ) ? sanitize_key( $_REQUEST['_wpnonce'] ) : '';
        // Use the correct name attribute from column_cb ('brief_ids[]')
        $brief_ids = isset( $_REQUEST['brief_ids'] ) ? array_map( 'intval', $_REQUEST['brief_ids'] ) : array();

        if ( empty( $brief_ids ) || empty($action) ) {
            return;
        }

        // Verify nonce based on action
        $nonce_action = '';
        if ($action === 'approve') {
            $nonce_action = 'bulk-' . $this->_args['plural']; // Matches the hidden field WP generates
        } elseif ($action === 'trash') {
             $nonce_action = 'bulk-' . $this->_args['plural'];
        } elseif ($action === 'untrash') {
             $nonce_action = 'bulk-' . $this->_args['plural'];
        } elseif ($action === 'delete_permanently') {
             $nonce_action = 'bulk-' . $this->_args['plural'];
        }
        // Add nonce checks for other custom bulk actions if needed

        if ( !$nonce_action || ! wp_verify_nonce( $nonce, $nonce_action ) ) {
              wp_die( 'Nonce verification failed!' );
        }

        // Check user capabilities
        if ( ! current_user_can( 'edit_posts' ) ) {
              wp_die( 'You do not have permission to perform this action.' );
        }

        // Determine redirect URL early
        $redirect_url = remove_query_arg( array( 'action', 'action2', 'brief_ids', '_wpnonce', 'approved', 'trashed', 'untrashed', 'deleted' ), wp_get_referer() );
        if (!$redirect_url) {
             $redirect_url = admin_url( 'edit.php?post_type=' . ACB_POST_TYPE );
         }
        if (isset($_REQUEST['post_status'])) {
             $redirect_url = add_query_arg( 'post_status', sanitize_key($_REQUEST['post_status']), $redirect_url );
         }
         if (isset($_REQUEST['s'])) {
            $redirect_url = add_query_arg( 's', sanitize_text_field($_REQUEST['s']), $redirect_url );
        }


        $count = count( $brief_ids );

        switch ( $action ) {
            case 'approve': // Renamed from bulk_approve for consistency
                $approved_count = 0;
                $generation_count = 0;
                
                foreach ($brief_ids as $id) {
                    $current_status = get_post_meta($id, '_acb_status', true);
                    if (in_array($current_status, ['pending', 'error', ''])) {
                        if (update_post_meta($id, '_acb_status', 'approved')) {
                            $approved_count++;
                            
                            // Attempt to automatically trigger generation for each approved brief
                            $result = acb_trigger_content_generation($id);
                            if ($result === true) {
                                $generation_count++;
                            }
                        }
                    }
                }
                
                $redirect_url = add_query_arg([
                    'approved' => $approved_count,
                    'generated' => $generation_count
                ], $redirect_url);
                break;            

            case 'trash': // Uses standard WP trash function
                $trashed_count = 0;
                foreach ( $brief_ids as $id ) {
                    if ( wp_trash_post( $id ) ) {
                        $trashed_count++;
                    }
                }
                $redirect_url = add_query_arg( 'trashed', $trashed_count, $redirect_url );
                break;

            case 'untrash': // Uses standard WP untrash function
                $untrashed_count = 0;
                foreach ( $brief_ids as $id ) {
                    if ( wp_untrash_post( $id ) ) {
                        $untrashed_count++;
                    }
                }
                $redirect_url = add_query_arg( 'untrashed', $untrashed_count, $redirect_url );
                break;

            case 'delete_permanently': // Uses standard WP delete function
                $deleted_count = 0;
                foreach ( $brief_ids as $id ) {
                    if ( wp_delete_post( $id, true ) ) { // Force delete
                        $deleted_count++;
                    }
                }
                $redirect_url = add_query_arg( 'deleted', $deleted_count, $redirect_url );
                break;

            // Add case 'bulk_generate' here if you implement it

            default:
                return; // Do nothing for unknown actions
        }

        // Redirect after processing bulk action
        wp_redirect( $redirect_url );
        exit;
    }
     // --- END MERGED process_bulk_action() ---


    // --- Keep existing column_cb() ---
    /**
     * Render the checkbox column.
     * @param array $item
     * @return string
     */
    protected function column_cb( $item ) {
        // Use 'brief_ids[]' to match the bulk action processing logic
        return sprintf(
            '<input type="checkbox" name="brief_ids[]" value="%s" />', $item['ID']
        );
    }

    // --- Keep existing column_title() for row actions ---
    /**
     * Render the title column with actions.
     * @param array $item
     * @return string
     */
    protected function column_title($item) {
        // ADD THIS AT THE TOP OF THE METHOD
        $post_id = $item['ID'];
        $status_from_db = get_post_meta($post_id, '_acb_status', true);
        error_log("DEBUG BRIEF ID: {$post_id}, Item Status: {$item['status']}, DB Status: {$status_from_db}");
        // END ADDITION
        $title = '<strong>';
        $edit_link = get_edit_post_link( $item['ID'] );
        if ($edit_link) {
            $title .= '<a class="row-title" href="' . esc_url($edit_link) . '">' . esc_html( $item['title'] ) . '</a>';
        } else {
            $title .= esc_html( $item['title'] );
        }
        $title .= '</strong>';

        $post_status = $item['post_status']; // Use fetched post status

        // Add post status label (Draft, Pending, etc.)
         if ( 'draft' === $post_status ) {
             $title .= ' — <span class="post-state">' . __( 'Draft' ) . '</span>';
         } elseif ( 'pending' === $post_status ) {
             $title .= ' — <span class="post-state">' . __( 'Pending Review' ) . '</span>';
         } // Add more if needed


        // --- Build Row Actions ---
        $actions = array();
        $brief_id = $item['ID'];
        $current_workflow_status = $item['status']; // Use the meta status

        if ($post_status !== 'trash') {
            // Edit Link
            if ($edit_link) {
                 $actions['edit'] = sprintf( '<a href="%s">%s</a>', esc_url($edit_link), __( 'Edit Brief' ) );
            }

            // Approve Link
            if ( in_array( $current_workflow_status, ['pending', 'error', ''] ) ) {
                $approve_nonce = wp_create_nonce( 'acb_approve_brief_' . $brief_id );
                $actions['approve'] = sprintf(
                    '<a href="#" class="acb-action-approve" data-brief-id="%d" data-nonce="%s">%s</a>',
                    $brief_id, $approve_nonce, __( 'Approve', 'ai-content-briefs' )
                );
            }

             // Generate Content Link
             if ( $current_workflow_status === 'approved' ) {
                 $generate_nonce = wp_create_nonce( 'acb_generate_content_' . $brief_id );
                 $actions['generate'] = sprintf(
                     '<a href="#" class="acb-action-generate" data-brief-id="%d" data-nonce="%s">%s</a>',
                     $brief_id, $generate_nonce, __( 'Generate Content', 'ai-content-briefs' )
                 );
             }

             // View/Edit Generated Post Link
             $generated_post_id = $item['generated_post_id'];
             if ($generated_post_id && ($gen_post = get_post($generated_post_id))) {
                  $gen_post_edit_link = get_edit_post_link($generated_post_id);
                  $gen_post_view_link = get_permalink($generated_post_id);
                  if ($gen_post_view_link && $gen_post->post_status === 'publish') {
                      $actions['view_post'] = sprintf('<a href="%s" target="_blank">%s</a>', esc_url($gen_post_view_link), __('View Post', 'ai-content-briefs'));
                  }
                  if ($gen_post_edit_link) {
                       $actions['edit_post'] = sprintf('<a href="%s" target="_blank">%s</a>', esc_url($gen_post_edit_link), __('Edit Post', 'ai-content-briefs'));
                   }
              }

             // Trash Link
             $actions['trash'] = sprintf(
                 '<a href="%s" class="submitdelete">%s</a>',
                 get_delete_post_link( $brief_id ), // Use standard WP delete link function
                 __( 'Trash' )
             );
        } else { // Actions for Trash view
            // Restore action
            $actions['untrash'] = sprintf(
                '<a href="%s">%s</a>',
                wp_nonce_url( admin_url( sprintf( 'post.php?post=%d&action=untrash', $brief_id ) ), 'untrash-post_' . $brief_id ),
                __( 'Restore' )
            );
            // Delete Permanently action
            $actions['delete'] = sprintf(
                '<a href="%s" class="submitdelete">%s</a>',
                 get_delete_post_link( $brief_id, '', true ), // Force delete = true
                 __( 'Delete Permanently' )
            );
        }

        return $title . $this->row_actions( $actions );
    }


    // --- !!! REPLACE existing column_status with this one !!! ---
    /**
     * Render the Status column with interactive dropdown.
     *
     * @param array $item
     * @return string
     */
     protected function column_status( $item ) {
         $current_status = esc_attr( $item['status'] );
         $brief_id = $item['ID'];
         $nonce = wp_create_nonce( 'acb_update_status_' . $brief_id );

         // Disable dropdown if status is 'generating'
         $disabled_attr = ($current_status === 'generating') ? 'disabled="disabled"' : '';

         $output = sprintf(
             '<select name="acb_status_%d" class="acb-status-select" data-brief-id="%d" data-nonce="%s" %s style="width: 120px;">',
             $brief_id,
             $brief_id,
             $nonce,
             $disabled_attr // Add disabled attribute if needed
         );

         foreach ( $this->status_options as $value => $label ) {
             // Don't allow selecting 'generating' manually (also handled by $disabled_attr on select)
             $option_disabled = ($value === 'generating' && $current_status !== 'generating') ? 'disabled' : '';
             $selected = selected( $current_status, $value, false );
             $output .= sprintf(
                 '<option value="%s" %s %s>%s</option>',
                 esc_attr( $value ),
                 $selected,
                 $option_disabled,
                 esc_html( $label )
             );
         }

         $output .= '</select>';
         $output .= '<span class="spinner" style="float: none; vertical-align: middle; margin-left: 5px; visibility: hidden;"></span>'; // Spinner hidden initially

         return $output;
     }
     // --- !!! END REPLACE column_status !!! ---
     
    // --- ADD method for the new column ---
    /**
     * Render the Content URL column.
     * @param array $item
     * @return string
     */
    protected function column_content_url( $item ) {
        $url = $item['content_url'];
        if ( $url ) {
            // Make it a clickable link
            return sprintf('<a href="%s" target="_blank" title="%s">%s</a>',
                esc_url( $url ),
                esc_attr( $url ),
                esc_html( wp_basename( untrailingslashit($url) ) ?: substr($url, 0, 30).'...' ) // Show filename or truncated URL
            );
        }
        return '—'; // Dash if no URL
    }
    // --- END ADD ---

    // --- Keep existing column_priority (modified slightly) ---
    protected function column_priority( $item ) {
        $priority = esc_html( $item['priority'] );
        $priority_map = array( '1' => '1 (High)', '2' => '2', '3' => '3 (Medium)', '4' => '4', '5' => '5 (Low)' );
        return isset($priority_map[$priority]) ? $priority_map[$priority] : ($priority ?: '3'); // Default display to 3 if empty
    }

    // --- ADD Methods for rendering NEW columns ---
    /**
     * Render the Opportunity Score column.
     * @param array $item
     * @return string
     */
    protected function column_opportunity_score( $item ) {
        $score = $item['opportunity_score'];
        return is_numeric( $score ) ? number_format_i18n( (float)$score, 1 ) : 'N/A';
    }

    /**
     * Render the Avg. Position column.
     * @param array $item
     * @return string
     */
    protected function column_avg_position( $item ) {
        $position = $item['avg_position'];
         return is_numeric( $position ) ? number_format_i18n( (float)$position, 2 ) : 'N/A';
    }

     /**
      * Render the Content Recommendation column.
      * @param array $item
      * @return string
      */
     protected function column_content_recommendation( $item ) {
         $recommendation = $item['content_recommendation'];
         return esc_html( ucwords( str_replace( '_', ' ', $recommendation ) ) ?: 'N/A' );
     }
     // --- END ADD New Column Methods ---

    // --- Keep existing column_date() ---
    protected function column_date( $item ) {
        return esc_html( $item['date'] );
    }

    // --- Keep existing column_generated_post() ---
     protected function column_generated_post( $item ) {
        $post_id = $item['generated_post_id'];
        if ( $post_id && $post = get_post($post_id) ) {
            $post_status_obj = get_post_status_object( $post->post_status ); // Use object
            $edit_link = get_edit_post_link( $post_id );
            $view_link = get_permalink( $post_id );
            $status_label = $post_status_obj ? esc_html($post_status_obj->label) : esc_html($post->post_status); // Safer label fetching

            $output = sprintf('<a href="%s" target="_blank">%s</a><br/>(%s)', esc_url($view_link), esc_html($post->post_title), $status_label);
            if ($edit_link) {
                // Don't show edit link for trash status
                 if ($post->post_status !== 'trash') {
                     $output .= sprintf(' <a href="%s" target="_blank">[Edit]</a>', esc_url($edit_link));
                 }
            }
            return $output;
        }
        return '—';
    }

        // --- ADD Rendering Methods for Original Columns ---
    /**
     * Render the Search Intent column.
     * @param array $item
     * @return string
     */
    protected function column_intent( $item ) {
        return esc_html( $item['intent'] ?: 'N/A' );
   }

   /**
    * Render the Volume (Monthly Searches) column.
    * @param array $item
    * @return string
    */
   protected function column_volume( $item ) {
       return is_numeric($item['volume']) ? number_format_i18n( (int)$item['volume'] ) : 'N/A';
   }

    /**
    * Render the Target Word Count column.
    * @param array $item
    * @return string
    */
   protected function column_target_wc( $item ) {
       return is_numeric($item['target_wc']) ? number_format_i18n( (int)$item['target_wc'] ) : 'N/A';
   }
   // --- END ADD ---

    // --- Keep existing no_items() ---
    public function no_items() {
        _e( 'No Content Briefs found.', 'ai-content-briefs' );
    }

    // --- REMOVE column_default - specific handlers cover all columns ---
    // public function column_default( $item, $column_name ) { ... }

} // End class