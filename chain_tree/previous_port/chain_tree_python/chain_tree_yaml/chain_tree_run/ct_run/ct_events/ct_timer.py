import time
from datetime import datetime, timezone
from .ct_events import CT_Events
class CT_Timer(CT_Events):
    """
    Custom Timer class that provides waiting functionality and comprehensive time information in GMT.
    """
    
    def __init__(self, wait_seconds):
        CT_Events.__init__(self)
        """Initialize the CT_Timer class."""
        self._last_time_info = None
        self.wait_seconds = wait_seconds
        self.tick_dict = {}
        self.tick_dict["time_tick"] = wait_seconds
        
    def add_dict_dict(self,field_name,value):
        self.tick_dict[field_name] = value
        
    def wait_timer(self, wait_seconds):
        """
        Waits for a specified period of time and returns comprehensive time information in GMT.
        
        Args:
            wait_seconds (float): Number of seconds to wait (can be fractional)
        
        Returns:
            dict: Dictionary containing:
                - year: Year (e.g., 2024)
                - month: Month (1-12)
                - day: Day of month (1-31)
                - dow: Day of week (0=Monday, 1=Tuesday, ..., 6=Sunday)
                - doy: Day of year (1-366)
                - hour: Hour (0-23)
                - minute: Minute (0-59)
                - second: Second (0-59)
                - timestamp: Unix timestamp (seconds since epoch)
        """
        
        # Wait for the specified duration
        time.sleep(wait_seconds)
        
        # Get the time after waiting
        new_time = datetime.now(timezone.utc)
        
        # Return comprehensive time information
        return {
            'year': new_time.year,
            'month': new_time.month,
            'day': new_time.day,
            'dow': new_time.weekday(),  # 0=Monday, 6=Sunday
            'doy': new_time.timetuple().tm_yday,  # Day of year
            'hour': new_time.hour,
            'minute': new_time.minute,
            'second': new_time.second,
            'timestamp': int(new_time.timestamp())  # Unix timestamp in seconds
        }
    def get_timestamp(self):
        """
        Returns the current timestamp in seconds since the epoch.
        """
        return (datetime.now(timezone.utc).timestamp())
    
    def get_current_time(self):
        """
        Returns current time information in GMT without waiting.
        
        Returns:
            dict: Same format as wait_timer but for current time
        """
        current_time = datetime.now(timezone.utc)
        
        return {
            'year': current_time.year,
            'month': current_time.month,
            'day': current_time.day,
            'dow': current_time.weekday(),  # 0=Monday, 6=Sunday
            'doy': current_time.timetuple().tm_yday,  # Day of year
            'hour': current_time.hour,
            'minute': current_time.minute,
            'second': current_time.second,
            'timestamp': current_time.timestamp()  # Unix timestamp in seconds
        }
    
    def format_time_info(self, time_info):
        """
        Formats time information dictionary into a readable string.
        
        Args:
            time_info (dict): Time information dictionary from wait_timer or get_current_time
            
        Returns:
            str: Formatted time string
        """
        dt = datetime.fromtimestamp(time_info['timestamp'], tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def timer_tick(self,all_start_nodes):
        """
        Calls wait_timer and returns only the GMT second and any values that have changed
        since the last call to timer_tick.
        
        Args:
            wait_seconds (float): Number of seconds to wait (can be fractional)
            
        Returns:
            dict: Dictionary containing:
                - second: Current GMT second (always returned)
                - changed: Dictionary of only the time components that changed
                - all_values: Complete time info (for reference)
        """
        # Get new time info after waiting
        current_info = self.wait_timer(self.wait_seconds)
        
        # Always include the second
        result = {
            
            'changed': {},
            'all_values': current_info
        }
        
        # If this is the first call, mark everything as changed
        if self._last_time_info is None:
            result['changed'] = {
                'second': current_info['second'],
                'year': current_info['year'],
                'month': current_info['month'], 
                'day': current_info['day'],
                'dow': current_info['dow'],
                'doy': current_info['doy'],
                'hour': current_info['hour'],
                'minute': current_info['minute'],
                'timestamp': current_info['timestamp']
            }
            
        else:
            # Compare with last time info and include only changed values
            time_fields = ['second','year', 'month', 'day', 'dow', 'doy', 'hour', 'minute', 'second','timestamp']
            
            for field in time_fields:
              
                if current_info[field] != self._last_time_info[field]:
                    result['changed'][field] = current_info[field]
        
        # Store current info for next comparison
        self._last_time_info = current_info.copy()
        self.tick_dict["time_stamp"] = current_info['timestamp']
        for start_node in all_start_nodes:
            self.add_event(start_node,"CFL_TIMER_EVENT",self.tick_dict)

        for key, value in result['changed'].items():
           
            if key == 'second':
                
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_SECOND_EVENT", current_info['second'])
            if key == 'minute':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_MINUTE_EVENT", current_info['minute'])
            if key == 'hour':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_HOUR_EVENT", current_info['hour'])
            if key == 'day':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_DAY_EVENT", current_info['day'])
            if key == 'dow':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_DOW_EVENT", current_info['dow'])
            if key == 'doy':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_DOY_EVENT", current_info['doy'])
            if key == 'month':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_MONTH_EVENT", current_info['month'])
            if key == 'year':
                for start_node in all_start_nodes:
                    self.add_event(start_node,"CFL_YEAR_EVENT", current_info['year'])
        return result
    
    def format_tick_result(self, tick_result):
        """
        Formats timer_tick result into a readable string.
        
        Args:
            tick_result (dict): Result from timer_tick method
            
        Returns:
            str: Formatted string showing second and changes
        """
        lines = [f"GMT Second: {tick_result['second']}"]
        
        if tick_result['changed']:
            lines.append("Changed values:")
            for field, value in tick_result['changed'].items():
                if field == 'dow':
                    lines.append(f"  {field}: {value} (0=Mon, 6=Sun)")
                elif field == 'timestamp':
                    dt = datetime.fromtimestamp(value, tz=timezone.utc)
                    lines.append(f"  {field}: {value} ({dt.strftime('%Y-%m-%d %H:%M:%S %Z')})")
                else:
                    lines.append(f"  {field}: {value}")
        else:
            lines.append("No changes detected")
            
        return "\n".join(lines)

    def print_time_info(self, time_info):
        """
        Prints comprehensive time information in a formatted way.
        
        Args:
            time_info (dict): Time information dictionary from wait_timer or get_current_time
        """
        print(f"Year: {time_info['year']}")
        print(f"Month: {time_info['month']}")
        print(f"Day: {time_info['day']}")
        print(f"Day of Week: {time_info['dow']} (0=Mon, 6=Sun)")
        print(f"Day of Year: {time_info['doy']}")
        print(f"Hour: {time_info['hour']}")
        print(f"Minute: {time_info['minute']}")
        print(f"Second: {time_info['second']}")
        print(f"Unix Timestamp: {time_info['timestamp']}")
        print(f"Formatted GMT: {self.format_time_info(time_info)}")

# Example usage
if __name__ == "__main__":
    # Create timer instance
    timer = CT_Timer()
    
    print("=== Testing timer_tick method ===")
    
    # First call - everything will be marked as changed
    print("First tick (1 second wait):")
    tick1 = timer.timer_tick(1.0)
    print(timer.format_tick_result(tick1))
    
    print("\n" + "-"*40)
    
    # Second call - only changed values will be shown
    print("Second tick (1 second wait):")
    tick2 = timer.timer_tick(1.0)
    print(timer.format_tick_result(tick2))
    
    print("\n" + "-"*40)
    
    # Third call with longer wait to potentially change minute
    print("Third tick (58 second wait - might cross minute boundary):")
    tick3 = timer.timer_tick(58.0)
    print(timer.format_tick_result(tick3))
    
    print("\n" + "-"*40)
    
    # Multiple quick ticks to show only second changes
    print("Quick ticks (0.5 second waits):")
    for i in range(3):
        tick = timer.timer_tick(0.5)
        print(f"Tick {i+1}: Second={tick['second']}, Changes: {list(tick['changed'].keys())}")
    
    print("\n" + "="*50)
    print("=== Original functionality still works ===")
    
    # Original methods still work
    print("Current time (no wait):")
    current = timer.get_current_time()
    timer.print_time_info(current)
    
    print("\nWait 2 seconds:")
    result = timer.wait_timer(2.0)
    print(f"After waiting: {timer.format_time_info(result)}")