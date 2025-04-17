jQuery(document).ready(function($) {
    'use strict';

    console.log('>>> Admin Briefs JS Loaded and Ready! <<<'); 
    
    // --- Status Dropdown Styling Enhancement ---
    // This ensures the styling is applied even after AJAX updates
    function refreshStatusStyles() {
        $('.acb-status-select').each(function() {
            var $select = $(this);
            var currentStatus = $select.val();
            
            // Update the data attribute to match the current selection
            $select.attr('data-current-status', currentStatus);
            
            // You could also add dynamic class changes here if needed
            $select.removeClass('status-pending status-approved status-generating status-draft_ready status-published status-error status-skip')
                  .addClass('status-' + currentStatus);
        });
    }
    
    // Run once on page load
    refreshStatusStyles();
    
    // --- Status Dropdown Change Handler ---
    $('.wp-list-table').on('change', 'select.acb-status-select', function(e) {
        var $select = $(this);
        var $spinner = $select.siblings('.spinner');
        var briefId = $select.data('brief-id');
        var newStatus = $select.val(); // Get the newly selected value
        var nonce = $select.data('nonce');
        
        // Store the value before the AJAX call to revert on error
        var originalValue = $select.data('original-value');
        if (originalValue === undefined) { // Store it the first time
            originalValue = $select.find('option:selected').val();
            $select.data('original-value', originalValue);
        }

        if ($select.find('option:selected').prop('disabled')) {
            alert('Status cannot be changed while generating.');
            $select.val(originalValue);
            return;
        }

        $spinner.addClass('is-active').css('visibility', 'visible');
        $select.prop('disabled', true);

        var data = {
            action: 'acb_update_status',
            brief_id: briefId,
            new_status: newStatus,
            _ajax_nonce: nonce
        };

        $.post(acb_ajax_object.ajax_url, data, function(response) {
            if (response.success) {
                $select.closest('td').addClass('status-updated');
                
                // Update the stored original value for future changes
                $select.data('original-value', newStatus);
                
                // Update data-current-status attribute for CSS targeting
                $select.attr('data-current-status', newStatus);
                
                // Add a small success indicator
                $select.parent().find('.status-update-msg').remove();
                $select.after('<span class="status-update-msg" style="color: green; margin-left: 5px;">✓ Saved</span>');
                setTimeout(function() { 
                    $select.parent().find('.status-update-msg').fadeOut(function() {
                        $(this).remove();
                    }); 
                }, 2000);
                
                // After 2 seconds, remove the animation class
                setTimeout(function() {
                    $select.closest('td').removeClass('status-updated');
                }, 2000);
            } else {
                alert('Error updating status: ' + (response.data ? response.data.message : acb_ajax_object.error_message));
                // Revert dropdown on error
                $select.val(originalValue);
                $select.attr('data-current-status', originalValue);
            }
        }).fail(function() {
            alert(acb_ajax_object.error_message);
            // Revert dropdown on failure
            $select.val(originalValue);
            $select.attr('data-current-status', originalValue);
        }).always(function() {
            $spinner.removeClass('is-active').css('visibility', 'hidden');
            $select.prop('disabled', false);
        });
    });

    // --- Approve Action ---
    $('.wp-list-table').on('click', 'a.acb-action-approve', function(e) {
        e.preventDefault(); // Prevent default link behavior

        var $link = $(this);
        var briefId = $link.data('brief-id');
        var nonce = $link.data('nonce');

        // Add visual feedback (optional)
        $link.text('Approving...');
        $link.css('pointer-events', 'none'); // Disable link temporarily

        // Prepare AJAX data
        var data = {
            action: 'acb_approve_brief', // Matches PHP action hook
            brief_id: briefId,
            _ajax_nonce: nonce // Nonce for verification
        };

        // Send AJAX request
        $.post(acb_ajax_object.ajax_url, data, function(response) {
            if (response.success) {
                // Update status display in the table row
                var $row = $link.closest('tr');
                $row.find('.acb-status').replaceWith(response.data.status_html);

                // Update row actions (remove approve, maybe show generate)
                // For simplicity, just remove the approve link for now
                // A full refresh or more complex DOM update might be needed for Generate link
                 $link.closest('.row-actions').find('.approve').remove(); // Remove the specific approve span

                // Or simply reload the page for simplicity until more actions are added
                // location.reload();
                 alert('Brief approved successfully!'); // Simple feedback

            } else {
                alert('Error: ' + (response.data ? response.data.message : acb_ajax_object.error_message));
                // Restore link on error
                $link.text('Approve');
                $link.css('pointer-events', 'auto');
            }
        }).fail(function() {
            alert(acb_ajax_object.error_message);
            // Restore link on failure
            $link.text('Approve');
            $link.css('pointer-events', 'auto');
        });
    });

    // --- Generate Content Action ---
    $('.wp-list-table').on('click', 'a.acb-action-generate', function(e) {
        e.preventDefault(); // Prevent default link behavior

        var $link = $(this);
        var briefId = $link.data('brief-id');
        var nonce = $link.data('nonce');

        // Add visual feedback
        $link.text('Generating...');
        $link.css('pointer-events', 'none'); // Disable link

        // Prepare AJAX data
        var data = {
            action: 'acb_generate_content', // Matches PHP action hook
            brief_id: briefId,
            _ajax_nonce: nonce // Nonce for verification
        };

        // Send AJAX request
        $.post(acb_ajax_object.ajax_url, data, function(response) {
            if (response.success) {
                 // Update status display in the table row
                 var $row = $link.closest('tr');
                 $row.find('.acb-status').replaceWith(response.data.status_html);

                 // Remove the generate link
                 $link.closest('.row-actions').find('.generate').remove();

                 alert('Content generation triggered! Status set to Generating.'); // Simple feedback

            } else {
                alert('Error: ' + (response.data ? response.data.message : acb_ajax_object.error_message));
                // Restore link on error
                $link.text('Generate Content');
                $link.css('pointer-events', 'auto');
            }
        }).fail(function() {
            alert(acb_ajax_object.error_message);
            // Restore link on failure
            $link.text('Generate Content');
            $link.css('pointer-events', 'auto');
        });
    });

    // --- TODO: Bulk Action Handling ---
    // Handling bulk actions purely with AJAX requires more involved JS
    // It often involves overriding the form submission or listening for the "Apply" click.
    // For now, bulk actions might still require a page reload as implemented in the List Table class.

});