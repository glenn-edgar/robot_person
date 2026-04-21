<%doc>
Workflow-specific macros for common patterns in LispSequencer
</%doc>

<%def name="retry_block(branch_id, max_retries)">
(@CFL_FORK ${branch_id})
(@SET_RETRY_COUNT ${max_retries})
(@LOG "Starting retry block ${branch_id} with max retries: ${max_retries}")
(!CFL_JOIN ${branch_id})
</%def>

<%def name="timeout_block(branch_id, timeout_seconds)">
(@CFL_FORK ${branch_id})
(!CFL_WAIT ${timeout_seconds})
(?TIMEOUT_CHECK ${branch_id})
(@CFL_TERMINATE ${branch_id})
</%def>

<%def name="error_handler(branch_id, error_message)">
(@CFL_FORK ${branch_id})
(@LOG_ERROR "${error_message}")
(@SEND_NOTIFICATION "error" "${error_message}")
(!CFL_JOIN ${branch_id})
</%def>

<%def name="sequential_steps(*step_names)">
% for i, step in enumerate(step_names):
(@CFL_FORK ${i})
(@EXECUTE_STEP "${step}")
(!CFL_JOIN ${i})
% endfor
</%def>

