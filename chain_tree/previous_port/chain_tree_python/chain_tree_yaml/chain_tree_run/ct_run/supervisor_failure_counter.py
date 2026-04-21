from collections import deque
from datetime import datetime, timedelta
from typing import Optional

class SupervisorFailureCounter:
    """
    Tracks failures within a sliding time window.
    Similar to Erlang's failure counting mechanism.
    """
    
    def __init__(self, max_failures: int, time_window_seconds: float):
        """
        Initialize the failure counter.
        
        Args:
            max_failures: Maximum number of failures allowed within the time window
            time_window_seconds: Time window in seconds to track failures
        """
        self.max_failures = max_failures
        self.time_window = timedelta(seconds=time_window_seconds)
        self.failures: deque = deque()  # Store failure timestamps
    
    def record_failure(self, timestamp: Optional[datetime] = None) -> None:
        """
        Record a failure occurrence.
        
        Args:
            timestamp: When the failure occurred (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.failures.append(timestamp)
        self._cleanup_old_failures(timestamp)
    
    def record_success(self, timestamp: Optional[datetime] = None) -> None:
        """
        Record a success - can be used to reset or clean up old failures.
        
        Args:
            timestamp: When the success occurred (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self._cleanup_old_failures(timestamp)
    
    def _cleanup_old_failures(self, current_time: datetime) -> None:
        """
        Remove failures that are outside the time window.
        
        Args:
            current_time: The current timestamp to use for calculation
        """
        cutoff_time = current_time - self.time_window
        
        # Remove failures older than the time window
        while self.failures and self.failures[0] < cutoff_time:
            self.failures.popleft()
    
    def is_threshold_exceeded(self, timestamp: Optional[datetime] = None) -> bool:
        """
        Check if the failure threshold has been exceeded.
        
        Args:
            timestamp: Current timestamp (defaults to now)
            
        Returns:
            True if failures >= max_failures within the time window
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self._cleanup_old_failures(timestamp)
        return len(self.failures) >= self.max_failures
    
    def get_failure_count(self, timestamp: Optional[datetime] = None) -> int:
        """
        Get the current number of failures within the time window.
        
        Args:
            timestamp: Current timestamp (defaults to now)
            
        Returns:
            Number of failures in the current window
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self._cleanup_old_failures(timestamp)
        return len(self.failures)
    
    def reset(self) -> None:
        """Clear all recorded failures."""
        self.failures.clear()


# Example usage and demonstration
if __name__ == "__main__":
    # Create a counter that allows max 3 failures within 10 seconds
    counter = SupervisorFailureCounter(max_failures=3, time_window_seconds=10)
    
    print("=== Example 1: Basic Usage ===")
    counter.record_failure()
    print(f"Failures after 1st failure: {counter.get_failure_count()}")
    
    counter.record_failure()
    print(f"Failures after 2nd failure: {counter.get_failure_count()}")
    
    counter.record_failure()
    print(f"Failures after 3rd failure: {counter.get_failure_count()}")
    print(f"Threshold exceeded? {counter.is_threshold_exceeded()}")
    
    print("\n=== Example 2: With Time Window ===")
    counter.reset()
    
    base_time = datetime.now()
    
    # Record 3 failures
    counter.record_failure(base_time)
    counter.record_failure(base_time + timedelta(seconds=2))
    counter.record_failure(base_time + timedelta(seconds=4))
    
    print(f"Failures at t=4s: {counter.get_failure_count(base_time + timedelta(seconds=4))}")
    print(f"Threshold exceeded at t=4s? {counter.is_threshold_exceeded(base_time + timedelta(seconds=4))}")
    
    # Check after time window expires
    print(f"Failures at t=15s: {counter.get_failure_count(base_time + timedelta(seconds=15))}")
    print(f"Threshold exceeded at t=15s? {counter.is_threshold_exceeded(base_time + timedelta(seconds=15))}")