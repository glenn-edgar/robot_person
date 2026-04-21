<%!
    import json
    
    def compress_json(data):
        """Replace quotes with --- for CFL string encoding."""
        return json.dumps(data).replace('"', '---')
%>

<%def name="send_system_event(event_name, event_data)">
(@CFL_SEND_SYSTEM_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>


<%def name="send_current_node_event(event_name, event_data)">
(@CFL_SEND_CURRENT_NODE_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>

