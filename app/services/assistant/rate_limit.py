"""
Per-user rate limiting for the Assistant.

Implements:
- Per-user token bucket for concurrent sessions (max 10)
- Per-user message rate limiting (100 messages / hour)

Uses in-memory storage by default. For multi-instance deployment,
use Redis as a shared backend.

Usage:
    limiter = RateLimiter()
    
    # Check concurrent session limit
    if not limiter.check_concurrent_sessions(user_id):
        raise HTTPException(429, "Too many concurrent sessions")
    
    # Check message rate limit
    if not limiter.check_message_rate(user_id):
        raise HTTPException(429, "Rate limit exceeded")
    
    # Record a message
    limiter.record_message(user_id)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting.
    
    Attributes:
        tokens: Current number of tokens available.
        max_tokens: Maximum number of tokens (bucket size).
        refill_rate: Tokens added per second.
        last_refill: Unix timestamp of last refill.
    """
    tokens: float
    max_tokens: float
    refill_rate: float
    last_refill: float = field(default_factory=time.time)
    
    def consume(self, count: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            count: Number of tokens to consume.
            
        Returns:
            True if tokens were consumed, False if insufficient tokens.
        """
        self._refill()
        
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


@dataclass
class SlidingWindowRateLimit:
    """
    Sliding window rate limiter for message counts.
    
    Tracks messages within a rolling time window.
    
    Attributes:
        timestamps: List of message timestamps.
        window_size: Size of the window in seconds.
        max_messages: Maximum messages allowed in the window.
    """
    timestamps: list[float] = field(default_factory=list)
    window_size: float = 3600.0  # 1 hour
    max_messages: int = 100
    
    def check(self) -> bool:
        """
        Check if a new message is allowed.
        
        Returns:
            True if message is allowed, False if rate limit exceeded.
        """
        self._cleanup()
        return len(self.timestamps) < self.max_messages
    
    def record(self) -> None:
        """Record a message timestamp."""
        self._cleanup()
        self.timestamps.append(time.time())
    
    def _cleanup(self) -> None:
        """Remove timestamps outside the window."""
        cutoff = time.time() - self.window_size
        self.timestamps = [ts for ts in self.timestamps if ts > cutoff]
    
    def remaining(self) -> int:
        """
        Get the number of messages remaining in the current window.
        
        Returns:
            Number of messages that can be sent before limit.
        """
        self._cleanup()
        return max(0, self.max_messages - len(self.timestamps))


class RateLimiter:
    """
    Per-user rate limiter for the Assistant.
    
    Implements:
    - Concurrent session limit: max 10 active sessions per user
    - Message rate limit: 100 messages per hour per user
    
    Thread-safe implementation using locks.
    """
    
    MAX_CONCURRENT_SESSIONS: int = 100
    MESSAGES_PER_HOUR: int = 100
    WINDOW_SIZE_SECONDS: float = 3600.0  # 1 hour
    
    _instance: RateLimiter | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> RateLimiter:
        """Singleton pattern for process-local rate limiting."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Initialize rate limiter state."""
        # Active sessions per user: user_id -> count
        self._active_sessions: dict[str, int] = {}

        # Message rate limits per user: user_id -> SlidingWindowRateLimit
        self._message_limits: dict[str, SlidingWindowRateLimit] = {}
        
        # Internal lock for thread safety
        self._data_lock = threading.Lock()
    
    def reset(self) -> None:
        """Reset all rate limiting state (for testing only)."""
        with self._data_lock:
            self._active_sessions.clear()
            self._message_limits.clear()
    
    def check_concurrent_sessions(self, user_id: UUID) -> bool:
        """
        Check if a user can start a new concurrent session.
        
        Args:
            user_id: The user ID.
            
        Returns:
            True if user can start a new session, False if limit exceeded.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            current = self._active_sessions.get(user_id_str, 0)
            return current < self.MAX_CONCURRENT_SESSIONS
    
    def record_session_started(self, user_id: UUID) -> None:
        """
        Record that a session has started.
        
        Args:
            user_id: The user ID.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            self._active_sessions[user_id_str] = self._active_sessions.get(user_id_str, 0) + 1
    
    def record_session_ended(self, user_id: UUID) -> None:
        """
        Record that a session has ended.
        
        Args:
            user_id: The user ID.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            if user_id_str in self._active_sessions:
                self._active_sessions[user_id_str] = max(0, self._active_sessions[user_id_str] - 1)
    
    def get_active_sessions(self, user_id: UUID) -> int:
        """
        Get the number of active sessions for a user.
        
        Args:
            user_id: The user ID.
            
        Returns:
            Number of active sessions.
        """
        with self._data_lock:
            return self._active_sessions.get(str(user_id), 0)
    
    def check_message_rate(self, user_id: UUID) -> bool:
        """
        Check if a user can send a message.
        
        Args:
            user_id: The user ID.
            
        Returns:
            True if message is allowed, False if rate limit exceeded.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            
            if user_id_str not in self._message_limits:
                self._message_limits[user_id_str] = SlidingWindowRateLimit(
                    window_size=self.WINDOW_SIZE_SECONDS,
                    max_messages=self.MESSAGES_PER_HOUR,
                )
            
            return self._message_limits[user_id_str].check()
    
    def record_message(self, user_id: UUID) -> None:
        """
        Record that a user has sent a message.
        
        Args:
            user_id: The user ID.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            
            if user_id_str not in self._message_limits:
                self._message_limits[user_id_str] = SlidingWindowRateLimit(
                    window_size=self.WINDOW_SIZE_SECONDS,
                    max_messages=self.MESSAGES_PER_HOUR,
                )
            
            self._message_limits[user_id_str].record()
    
    def get_message_remaining(self, user_id: UUID) -> int:
        """
        Get the number of messages remaining for a user.
        
        Args:
            user_id: The user ID.
            
        Returns:
            Number of messages that can be sent before limit.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            
            if user_id_str not in self._message_limits:
                return self.MESSAGES_PER_HOUR
            
            return self._message_limits[user_id_str].remaining()
    
    def get_concurrent_sessions_remaining(self, user_id: UUID) -> int:
        """
        Get the number of sessions a user can still start.
        
        Args:
            user_id: The user ID.
            
        Returns:
            Number of sessions that can be started before limit.
        """
        with self._data_lock:
            active = self._active_sessions.get(str(user_id), 0)
            return max(0, self.MAX_CONCURRENT_SESSIONS - active)
    
    def get_limits_info(self, user_id: UUID) -> dict:
        """
        Get rate limit information for a user.

        Args:
            user_id: The user ID.

        Returns:
            Dictionary with rate limit information.
        """
        with self._data_lock:
            user_id_str = str(user_id)
            active = self._active_sessions.get(user_id_str, 0)

            # Calculate remaining directly to avoid deadlock
            concurrent_remaining = max(0, self.MAX_CONCURRENT_SESSIONS - active)

            # Get message remaining
            if user_id_str in self._message_limits:
                message_remaining = self._message_limits[user_id_str].remaining()
            else:
                message_remaining = self.MESSAGES_PER_HOUR

            return {
                "user_id": str(user_id),
                "concurrent_sessions": {
                    "active": active,
                    "max": self.MAX_CONCURRENT_SESSIONS,
                    "remaining": concurrent_remaining,
                },
                "message_rate": {
                    "remaining": message_remaining,
                    "max_per_hour": self.MESSAGES_PER_HOUR,
                },
            }


# Global rate limiter instance
rate_limiter = RateLimiter()
