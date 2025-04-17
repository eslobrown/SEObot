<?php
/**
 * Adds and handles Meta Boxes for the Content Brief CPT.
 */

// Exit if accessed directly.
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Register meta boxes for the Content Brief CPT.
 * This function is called by the hook at the bottom of the file.
 */
function acb_add_meta_boxes() {
    add_meta_box(
        'acb_brief_details_metabox', // Unique ID for the meta box
        __( 'Brief Details & Status', 'ai-content-briefs' ), // Title
        'acb_display_brief_details_metabox_content', // Callback function
        ACB_POST_TYPE, // Post type
        'normal', // Context (normal = main column)
        'high' // Priority
    );

    add_meta_box(
        'acb_prompt_metabox', // Unique ID
        __( 'AI Generation Prompt', 'ai-content-briefs' ), // Title
        'acb_display_prompt_metabox_content', // Callback
        ACB_POST_TYPE, // Post type
        'normal', // Context
        'default' // Priority
    );

     add_meta_box(
        'acb_results_metabox', // Unique ID
        __( 'Generation Results & Tracking', 'ai-content-briefs' ), // Title
        'acb_display_results_metabox_content', // Callback
        ACB_POST_TYPE, // Post type
        'side', // Context (side column)
        'default' // Priority
    );
}


/**
 * Display the content for the Brief Details & Status meta box.
 *
 * @param WP_Post $post The current post object.
 */
function acb_display_brief_details_metabox_content( $post ) {
    // Add a nonce field for security verification upon saving
    wp_nonce_field( 'acb_save_brief_details_metabox_data', 'acb_brief_details_metabox_nonce' );

    // --- Get ALL current saved values (or defaults) ---
    $keyword = get_post_meta( $post->ID, '_acb_keyword', true );
    $status = get_post_meta( $post->ID, '_acb_status', true ) ?: 'pending';
    $priority = get_post_meta( $post->ID, '_acb_priority', true ) ?: '3';
    $intent = get_post_meta( $post->ID, '_acb_search_intent', true ) ?: 'informational';
    $volume = get_post_meta( $post->ID, '_acb_monthly_searches', true );
    $target_wc = get_post_meta( $post->ID, '_acb_target_word_count', true );
    $notes = get_post_meta( $post->ID, '_acb_notes', true );
    $current_position = get_post_meta( $post->ID, '_acb_current_position', true );
    $content_recommendation = get_post_meta( $post->ID, '_acb_content_recommendation', true );
    $opportunity_score = get_post_meta( $post->ID, '_acb_opportunity_score', true );
    $total_impressions = get_post_meta( $post->ID, '_acb_total_impressions', true );
    $total_clicks = get_post_meta( $post->ID, '_acb_total_clicks', true );
    $content_url = get_post_meta( $post->ID, '_acb_content_url', true ); // <-- Get the new value
    $recommendation = get_post_meta($post->ID, '_acb_content_recommendation', true) ?: 'create_new';
    $category_id = get_post_meta($post->ID, '_acb_target_category_id', true) ?: '';
    $claude_prompt = get_post_meta($post->ID, '_acb_claude_prompt', true) ?: '';


    // --- Define status options ---
    $status_options = array(
        'pending'     => __( 'Pending', 'ai-content-briefs' ),
        'approved'    => __( 'Approved', 'ai-content-briefs' ),
        'generating'  => __( 'Generating (Locked)', 'ai-content-briefs' ),
        'draft_ready' => __( 'Draft Ready', 'ai-content-briefs' ),
        'published'   => __( 'Published', 'ai-content-briefs' ),
        'error'       => __( 'Error', 'ai-content-briefs' ),
        'skip'        => __( 'Skip', 'ai-content-briefs' ),
    );
    // --- Define priority options ---
    $priority_options = array(
        '1' => __( '1 (High)', 'ai-content-briefs' ),
        '2' => __( '2', 'ai-content-briefs' ),
        '3' => __( '3 (Medium)', 'ai-content-briefs' ),
        '4' => __( '4', 'ai-content-briefs' ),
        '5' => __( '5 (Low)', 'ai-content-briefs' ),
    );
    // --- Define intent options ---
    $intent_options = array(
        'informational' => __( 'Informational', 'ai-content-briefs' ),
        'commercial'    => __( 'Commercial', 'ai-content-briefs' ),
        'navigational'  => __( 'Navigational', 'ai-content-briefs' ),
        'transactional' => __( 'Transactional', 'ai-content-briefs' ),
    );

    ?>
    <style>
        /* Simple style for read-only fields */
        .acb-read-only-field { background-color: #f0f0f0; color: #555; cursor: not-allowed; }
        .form-table th { width: 180px; } /* Adjust label column width */
    </style>
    <table class="form-table">
        <tbody>
            <!-- Keyword (Editable) -->
            <tr>
                <th scope="row"><label for="acb_keyword_field"><?php esc_html_e( 'Keyword', 'ai-content-briefs' ); ?></label></th>
                <td><input type="text" id="acb_keyword_field" name="acb_keyword_field" value="<?php echo esc_attr( $keyword ); ?>" class="regular-text" required /></td>
            </tr>

            <!-- Workflow Status (Conditionally Editable) -->
             <tr>
                <th scope="row"><label for="acb_status_field"><?php esc_html_e( 'Workflow Status', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <select name="acb_status_field" id="acb_status_field" <?php disabled( $status, 'generating' ); ?>>
                        <?php foreach ( $status_options as $value => $label ) : ?>
                            <option value="<?php echo esc_attr( $value ); ?>" <?php selected( $status, $value ); ?> <?php disabled( $value, 'generating', ($status !== 'generating') ); /* Also disable generating option unless it's the current status */ ?>><?php echo esc_html( $label ); ?></option>
                        <?php endforeach; ?>
                    </select>
                     <?php if ($status === 'generating'): ?>
                        <p class="description"><i><?php esc_html_e( 'Status locked while content generation is in progress.', 'ai-content-briefs' ); ?></i></p>
                    <?php else: ?>
                         <p class="description"><?php esc_html_e( 'Set to "Approved" to allow generation. Use "Skip" to ignore.', 'ai-content-briefs' ); ?></p>
                    <?php endif; ?>
                </td>
            </tr>

            <!-- Priority (Editable) -->
             <tr>
                <th scope="row"><label for="acb_priority_field"><?php esc_html_e( 'Priority', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <select name="acb_priority_field" id="acb_priority_field">
                         <?php foreach ( $priority_options as $value => $label ) : ?>
                            <option value="<?php echo esc_attr( $value ); ?>" <?php selected( $priority, $value ); ?>><?php echo esc_html( $label ); ?></option>
                        <?php endforeach; ?>
                    </select>
                    <p class="description"><?php esc_html_e( 'Priority for content creation (1=High).', 'ai-content-briefs' ); ?></p>
                </td>
            </tr>

             <!-- Search Intent (Editable) -->
            <tr>
                <th scope="row"><label for="acb_search_intent_field"><?php esc_html_e( 'Search Intent', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <select name="acb_search_intent_field" id="acb_search_intent_field">
                         <?php foreach ( $intent_options as $value => $label ) : ?>
                            <option value="<?php echo esc_attr( $value ); ?>" <?php selected( $intent, $value ); ?>><?php echo esc_html( $label ); ?></option>
                        <?php endforeach; ?>
                    </select>
                     <p class="description"><?php esc_html_e( 'Estimated user intent.', 'ai-content-briefs' ); ?></p>
               </td>
            </tr>

            <!-- Monthly Searches (Editable) -->
            <tr>
                <th scope="row"><label for="acb_monthly_searches_field"><?php esc_html_e( 'Monthly Searches (Est.)', 'ai-content-briefs' ); ?></label></th>
                <td><input type="number" id="acb_monthly_searches_field" name="acb_monthly_searches_field" value="<?php echo esc_attr( $volume ); ?>" class="small-text" min="0" step="1" /></td>
            </tr>

             <!-- Target Word Count (Editable) -->
             <tr>
                <th scope="row"><label for="acb_target_word_count_field"><?php esc_html_e( 'Target Word Count', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <input type="number" id="acb_target_word_count_field" name="acb_target_word_count_field" value="<?php echo esc_attr( $target_wc ); ?>" class="small-text" min="100" step="50" required/>
                     <p class="description"><?php esc_html_e( 'Recommended length (from analysis/AI).', 'ai-content-briefs' ); ?></p>
                </td>
            </tr>
            
            <!-- Content URL (Editable) -->
            <tr>
                <th scope="row"><label for="acb_content_url_field"><?php esc_html_e( 'Content URL', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <input type="url" id="acb_content_url_field" name="acb_content_url_field" value="<?php echo esc_url( $content_url ); ?>" class="regular-text" placeholder="<?php esc_attr_e( 'Enter URL of published post or leave blank if auto-generated', 'ai-content-briefs' ); ?>" />
                    <p class="description"><?php esc_html_e( 'URL of the final content (manual or auto-filled).', 'ai-content-briefs' ); ?></p>
                </td>
            </tr>

            <tr>
                <th scope="row"><label for="acb_content_recommendation_field"><?php esc_html_e('Content Recommendation', 'ai-content-briefs'); ?></label></th>
                <td>
                    <select name="acb_content_recommendation_field" id="acb_content_recommendation_field" class="acb-recommendation-select">
                        <option value="create_new" <?php selected($recommendation, 'create_new'); ?>><?php esc_html_e('Create New Content', 'ai-content-briefs'); ?></option>
                        <option value="dual_content" <?php selected($recommendation, 'dual_content'); ?>><?php esc_html_e('Dual Content (Category + Blog)', 'ai-content-briefs'); ?></option>
                    </select>
                    <div id="acb_category_id_container" style="<?php echo ($recommendation !== 'dual_content') ? 'display:none;' : ''; ?> margin-top: 8px;">
                        <label for="acb_target_category_id_field"><?php esc_html_e('Category ID:', 'ai-content-briefs'); ?></label>
                        <input type="number" id="acb_target_category_id_field" name="acb_target_category_id_field" value="<?php echo esc_attr($category_id); ?>" class="small-text" min="1" />
                        <p class="description"><?php esc_html_e('Enter the product category ID to update.', 'ai-content-briefs'); ?></p>
                    </div>
                    
                    <!-- Add Update Prompt Button -->
                    <div style="margin-top: 15px;">
                        <button type="button" id="acb_update_prompt_btn" class="button button-secondary">
                            <?php esc_html_e('Update Claude Prompt for Selected Mode', 'ai-content-briefs'); ?>
                        </button>
                        <span id="acb_prompt_update_spinner" class="spinner" style="float: none; vertical-align: middle;"></span>
                        <div id="acb_prompt_update_message" style="margin-top: 8px;"></div>
                    </div>
                </td>
            </tr>

            <!-- Notes (Editable) -->
            <tr>
                <th scope="row"><label for="acb_notes_field"><?php esc_html_e( 'Notes', 'ai-content-briefs' ); ?></label></th>
                <td>
                    <textarea id="acb_notes_field" name="acb_notes_field" rows="4" class="large-text"><?php echo esc_textarea( $notes ); ?></textarea>
                     <p class="description"><?php esc_html_e( 'Internal notes about this brief.', 'ai-content-briefs' ); ?></p>
               </td>
            </tr>

            <tr style="border-top: 1px solid #ddd;">
                 <th scope="row" colspan="2"><strong><?php esc_html_e('Analysis & Metrics (Read-Only)', 'ai-content-briefs'); ?></strong></th>
            </tr>

            <!-- Current Position -->
            <tr>
                <th scope="row"><?php esc_html_e( 'Avg. GSC Position', 'ai-content-briefs' ); ?></th>
                <td><input type="text" value="<?php echo esc_attr( is_numeric($current_position) ? number_format_i18n( (float)$current_position, 2 ) : 'N/A' ); ?>" class="small-text acb-read-only-field" readonly /></td>
            </tr>

            <!-- Content Recommendation -->
            <tr>
                <th scope="row"><?php esc_html_e( 'Content Recommendation', 'ai-content-briefs' ); ?></th>
                <td><input type="text" value="<?php echo esc_attr( $content_recommendation ?: 'N/A' ); ?>" class="regular-text acb-read-only-field" readonly /></td>
            </tr>

             <!-- Opportunity Score -->
            <tr>
                <th scope="row"><?php esc_html_e( 'Opportunity Score', 'ai-content-briefs' ); ?></th>
                <td><input type="text" value="<?php echo esc_attr( is_numeric($opportunity_score) ? number_format_i18n( (float)$opportunity_score, 1 ) : 'N/A' ); ?>" class="small-text acb-read-only-field" readonly /></td>
            </tr>

             <!-- GSC Clicks / Impressions -->
             <tr>
                 <th scope="row"><?php esc_html_e( 'GSC Clicks / Impressions', 'ai-content-briefs' ); ?></th>
                 <td>
                     <input type="text" value="<?php echo esc_attr( number_format_i18n((int)$total_clicks) ); ?>" class="small-text acb-read-only-field" readonly size="5"/> /
                     <input type="text" value="<?php echo esc_attr( number_format_i18n((int)$total_impressions) ); ?>" class="small-text acb-read-only-field" readonly size="7"/>
                 </td>
            </tr>

        </tbody>
    </table>

    <!-- Add JavaScript to show/hide the category ID field -->
    <script type="text/javascript">
    jQuery(document).ready(function($) {
        // Toggle category ID field visibility
        $('#acb_content_recommendation_field').on('change', function() {
            if ($(this).val() === 'dual_content') {
                $('#acb_category_id_container').show();
            } else {
                $('#acb_category_id_container').hide();
            }
        });
        
        // Handle prompt update button click
        $('#acb_update_prompt_btn').on('click', function() {
            const $button = $(this);
            const $spinner = $('#acb_prompt_update_spinner');
            const $message = $('#acb_prompt_update_message');
            const briefId = $('#post_ID').val();
            const recommendation = $('#acb_content_recommendation_field').val();
            const categoryId = $('#acb_target_category_id_field').val();
            
            // Validate inputs
            if (recommendation === 'dual_content' && !categoryId) {
                $message.html('<div class="notice notice-error inline"><p>Please enter a Category ID for dual content.</p></div>');
                return;
            }
            
            // Disable button and show spinner
            $button.prop('disabled', true);
            $spinner.addClass('is-active');
            $message.html('');
            
            // Call AJAX to update prompt
            $.ajax({
                url: ajaxurl,
                type: 'POST',
                data: {
                    action: 'acb_update_prompt',
                    brief_id: briefId,
                    recommendation: recommendation,
                    category_id: categoryId,
                    _ajax_nonce: '<?php echo wp_create_nonce('acb_update_prompt_nonce'); ?>'
                },
                success: function(response) {
                    if (response.success) {
                        $message.html('<div class="notice notice-success inline"><p>' + response.data.message + '</p></div>');
                        // Optionally reload the page to show updated meta
                        // window.location.reload();
                    } else {
                        $message.html('<div class="notice notice-error inline"><p>' + response.data.message + '</p></div>');
                    }
                },
                error: function() {
                    $message.html('<div class="notice notice-error inline"><p>Unknown error occurred while updating prompt.</p></div>');
                },
                complete: function() {
                    $button.prop('disabled', false);
                    $spinner.removeClass('is-active');
                }
            });
        });
    });
    </script>

    <?php
}

/**
 * Display the content for the AI Prompt meta box.
 *
 * @param WP_Post $post The current post object.
 */
function acb_display_prompt_metabox_content($post) {
    // Nonce is included in the other metabox, no need to repeat unless saving separately

    $prompt = get_post_meta( $post->ID, '_acb_claude_prompt', true );
    ?>
     <p>
        <label for="acb_claude_prompt_field"><strong><?php esc_html_e( 'Generated Prompt for AI:', 'ai-content-briefs' ); ?></strong></label>
    </p>
     <!-- Make the textarea read-only if you don't want users editing it -->
     <textarea id="acb_claude_prompt_field" name="acb_claude_prompt_field" rows="15" class="large-text" readonly><?php echo esc_textarea( $prompt ); ?></textarea>
     <p class="description"><?php esc_html_e( 'This prompt will be sent to the AI for content generation when triggered. It is not editable here.', 'ai-content-briefs' ); ?></p>
    <?php
}

/**
 * Display the content for the Results & Tracking meta box.
 *
 * @param WP_Post $post The current post object.
 */
function acb_display_results_metabox_content($post) {
     // Nonce is included in the other metabox

     $generated_post_id = get_post_meta( $post->ID, '_acb_generated_post_id', true );
     $generated_post_url = get_post_meta( $post->ID, '_acb_generated_post_url', true );
     $category_url = get_post_meta( $post->ID, '_acb_generated_category_url', true );
     $error_message = get_post_meta( $post->ID, '_acb_error_message', true );
     $task_id = get_post_meta( $post->ID, '_acb_pa_task_id', true );
     $draft_date = get_post_meta( $post->ID, '_acb_draft_date', true );
     $published_date = get_post_meta( $post->ID, '_acb_published_date', true );

     echo '<p>';
     if ($generated_post_id && $generated_post_url) {
         $post_link = get_edit_post_link($generated_post_id);
         if ($post_link) {
              printf(
                  wp_kses_post(__( 'Generated Post: <a href="%s" target="_blank">Edit Draft/Post (ID: %d)</a>', 'ai-content-briefs' )),
                  esc_url($post_link),
                  esc_html($generated_post_id)
              );
         } else {
              esc_html_e( 'Generated Post ID:', 'ai-content-briefs'); echo ' ' . esc_html($generated_post_id);
         }
     } elseif ($error_message) {
          echo '<strong>' . esc_html__( 'Error:', 'ai-content-briefs' ) . '</strong><br/>';
          echo '<em style="color: #d63638;">' . nl2br(esc_html( $error_message )) . '</em>'; // Display error
     } else {
         esc_html_e( 'No content generated yet.', 'ai-content-briefs');
     }
     echo '</p>';

    if ($category_url) {
         echo '<p>';
         printf(
             wp_kses_post(__( 'Updated Category: <a href="%s" target="_blank">View Category</a>', 'ai-content-briefs' )),
             esc_url($category_url)
         );
         echo '</p>';
    }

    if ($draft_date) {
         echo '<p><strong>' . esc_html__( 'Draft Created:', 'ai-content-briefs' ) . '</strong> ' . esc_html( date_i18n( get_option( 'date_format' ) . ' @ ' . get_option( 'time_format' ), strtotime( $draft_date ) ) ) . '</p>';
    }
     if ($published_date) {
         echo '<p><strong>' . esc_html__( 'Post Published:', 'ai-content-briefs' ) . '</strong> ' . esc_html( date_i18n( get_option( 'date_format' ) . ' @ ' . get_option( 'time_format' ), strtotime( $published_date ) ) ) . '</p>';
    }
     if ($task_id) {
         echo '<p><small>' . esc_html__( 'Task ID:', 'ai-content-briefs' ) . ' ' . esc_html($task_id) . '</small></p>';
    }
}


/**
 * Save the data from the Brief Details meta box.
 * Handles saving for ALL fields defined in that metabox.
 *
 * @param int $post_id The ID of the post being saved.
 */
function acb_save_brief_details_metabox_data( $post_id ) {

    // 1. Check nonce
    if ( ! isset( $_POST['acb_brief_details_metabox_nonce'] ) || ! wp_verify_nonce( sanitize_key($_POST['acb_brief_details_metabox_nonce']), 'acb_save_brief_details_metabox_data' ) ) {
        error_log("ACB Save: Nonce check failed for post ID $post_id");
        return;
    }

    // 2. Check autosave
    if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
        return;
    }

    // 3. Check permissions
    if ( ! current_user_can( 'edit_post', $post_id ) ) {
        error_log("ACB Save: Permission check failed for post ID $post_id");
        return;
    }

    // 4. Check post type
    if ( get_post_type($post_id) !== ACB_POST_TYPE ) {
        return;
    }

    // 5. Define fields that are EDITABLE in this meta box
    $editable_fields_to_save = array(
        'acb_keyword_field'             => '_acb_keyword',
        'acb_status_field'              => '_acb_status',
        'acb_priority_field'            => '_acb_priority',
        'acb_search_intent_field'       => '_acb_search_intent',
        'acb_monthly_searches_field'    => '_acb_monthly_searches',
        'acb_target_word_count_field'   => '_acb_target_word_count',
        'acb_notes_field'               => '_acb_notes',
        'acb_content_url_field'         => '_acb_content_url', // <-- ADDED TO SAVE
        //'acb_claude_prompt_field'       => '_acb_claude_prompt', // Removed - saved via Python, displayed read-only
    );

    // Loop through EDITABLE fields
    foreach ( $editable_fields_to_save as $field_name => $meta_key ) {
        if ( isset( $_POST[ $field_name ] ) ) {
            $value = $_POST[ $field_name ];

            // Sanitize based on expected type
            if ( in_array($meta_key, ['_acb_monthly_searches', '_acb_target_word_count']) ) {
                $sanitized_value = intval( $value );
            } elseif ($meta_key == '_acb_notes') { // Prompt is no longer saved here
                 $sanitized_value = sanitize_textarea_field( $value );
            } elseif ($meta_key == '_acb_content_url') { // Sanitize URL
                 $sanitized_value = esc_url_raw( trim( $value ) );
            } else {
                $sanitized_value = sanitize_text_field( $value );
            }

             // Prevent changing status away from 'generating' manually
             if ($meta_key === '_acb_status') {
                 $current_status = get_post_meta( $post_id, '_acb_status', true );
                 if ($current_status === 'generating' && $sanitized_value !== 'generating') {
                      // Don't update if trying to change away from 'generating'
                      error_log("ACB Save: Attempted to change status away from 'generating' for post ID $post_id - ignoring.");
                      continue;
                 }
            }

            update_post_meta( $post_id, $meta_key, $sanitized_value );
        }
    }
     // NOTE: We no longer save read-only fields like _acb_current_position here.
     // They are only saved when the brief is initially created by run_analysis.py.
}


// --- !!! MOVE HOOK CALL TO THE END !!! ---
// Use the specific hook for the CPT for efficiency
add_action( 'save_post_' . ACB_POST_TYPE, 'acb_save_brief_details_metabox_data' );
// --- END MOVE HOOK CALL ---

// Register the meta boxes
add_action( 'add_meta_boxes', 'acb_add_meta_boxes' );

?>