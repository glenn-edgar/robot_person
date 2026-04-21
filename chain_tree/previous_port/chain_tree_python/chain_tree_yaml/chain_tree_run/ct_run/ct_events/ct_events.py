from collections import deque
class CT_Events:
    def __init__(self):
        self.events = deque()
        self.event_id_counter = -1
        
    def add_event(self, node_id, event_id, event_data):
        self.event_id_counter += 1
        self.events.append({"node_id": node_id, "event_id": event_id, "event_data": event_data})
        
    def add_immediate_event(self, node_id, event_id, event_data):
        self.events.appendleft({"node_id": node_id, "event_id": event_id, "event_data": event_data})
        
    def event_queue_length(self):
        return len(self.events)
    
    def get_event(self, event_id):
        if event_id < 0:
            raise ValueError("Event queue is empty")
        return self.events[self.event_id_counter]
    
    def pop_event(self):
        if self.event_queue_length() < 0:
            raise ValueError("Event queue is empty")
        return_value = self.events.popleft()
        self.event_id_counter -= 1
        return return_value
    
    def clear_events_queue(self):
        self.events.clear()
        self.event_id_counter = -1
    
    def dump_events_queue(self):
        print("Event queue length", self.event_queue_length())
        for event in self.events:
            print("Event", event)
    