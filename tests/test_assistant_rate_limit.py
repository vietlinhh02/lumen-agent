"""Tests for the Assistant rate limiting module."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from app.services.assistant.rate_limit import (
    RateLimiter,
    SlidingWindowRateLimit,
    rate_limiter,
)


class TestSlidingWindowRateLimit:
    """Tests for SlidingWindowRateLimit."""

    def test_check_allows_under_limit(self):
        """Test that requests are allowed under the limit."""
        limiter = SlidingWindowRateLimit(window_size=3600, max_messages=100)

        # Should allow up to 100 messages
        for _ in range(100):
            assert limiter.check() is True
            limiter.record()

    def test_check_blocks_over_limit(self):
        """Test that requests are blocked over the limit."""
        limiter = SlidingWindowRateLimit(window_size=3600, max_messages=5)

        # Use up the limit
        for _ in range(5):
            limiter.record()

        # Next check should fail
        assert limiter.check() is False

    def test_remaining_calculation(self):
        """Test remaining messages calculation."""
        limiter = SlidingWindowRateLimit(window_size=3600, max_messages=10)

        assert limiter.remaining() == 10

        limiter.record()
        limiter.record()
        limiter.record()

        assert limiter.remaining() == 7

    def test_window_expiry(self):
        """Test that old messages expire after the window."""
        limiter = SlidingWindowRateLimit(window_size=0.1, max_messages=5)

        # Use up the limit
        for _ in range(5):
            limiter.record()

        assert limiter.check() is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be allowed again
        assert limiter.check() is True

    def test_multiple_record_calls(self):
        """Test recording multiple messages."""
        limiter = SlidingWindowRateLimit(window_size=3600, max_messages=10)

        limiter.record()
        limiter.record()
        limiter.record()

        assert len(limiter.timestamps) == 3
        assert limiter.remaining() == 7


class TestTokenBucket:
    """Tests for TokenBucket."""
    from app.services.assistant.rate_limit import TokenBucket

    def test_consume_succeeds_with_enough_tokens(self):
        """Test consuming tokens when available."""
        from app.services.assistant.rate_limit import TokenBucket

        bucket = TokenBucket(tokens=5, max_tokens=10, refill_rate=0)  # 0 refill rate to avoid floating point

        assert bucket.consume(3) is True
        assert bucket.tokens == pytest.approx(2, abs=0.01)

    def test_consume_fails_without_enough_tokens(self):
        """Test consuming tokens when insufficient."""
        from app.services.assistant.rate_limit import TokenBucket

        bucket = TokenBucket(tokens=2, max_tokens=10, refill_rate=0)  # 0 refill rate to avoid floating point

        assert bucket.consume(5) is False
        # Tokens unchanged when consume fails
        assert bucket.tokens == pytest.approx(2, abs=0.01)

    def test_refill_on_consume(self):
        """Test that tokens are refilled on consume."""
        from app.services.assistant.rate_limit import TokenBucket

        bucket = TokenBucket(tokens=1, max_tokens=10, refill_rate=10)

        time.sleep(0.1)  # Wait for refill

        # Should have more tokens now
        assert bucket.consume(2) is True


class TestRateLimiter:
    """Tests for RateLimiter singleton."""

    def setup_method(self):
        """Reset rate limiter before each test."""
        # Reset singleton state to ensure clean state for each test
        RateLimiter._instance = None
        rate_limiter.reset()

    def test_singleton_pattern(self):
        """Test that RateLimiter is a singleton."""
        r1 = RateLimiter()
        r2 = RateLimiter()
        assert r1 is r2

    def test_concurrent_sessions_allows_under_limit(self):
        """Test that sessions are allowed under the limit."""
        user_id = uuid4()

        # Should allow up to 100 concurrent sessions
        for _ in range(100):
            assert rate_limiter.check_concurrent_sessions(user_id) is True
            rate_limiter.record_session_started(user_id)

    def test_concurrent_sessions_blocks_over_limit(self):
        """Test that sessions are blocked over the limit."""
        user_id = uuid4()

        # Start 100 sessions (the limit)
        for _ in range(100):
            rate_limiter.record_session_started(user_id)

        # 101st session should be blocked
        assert rate_limiter.check_concurrent_sessions(user_id) is False

    def test_record_session_ended(self):
        """Test recording session end."""
        user_id = uuid4()

        rate_limiter.record_session_started(user_id)
        rate_limiter.record_session_started(user_id)
        assert rate_limiter.get_active_sessions(user_id) == 2

        rate_limiter.record_session_ended(user_id)
        assert rate_limiter.get_active_sessions(user_id) == 1

    def test_record_session_ended_never_goes_below_zero(self):
        """Test that active sessions never goes below zero."""
        user_id = uuid4()

        rate_limiter.record_session_ended(user_id)  # Should not go negative
        assert rate_limiter.get_active_sessions(user_id) == 0

    def test_message_rate_allows_under_limit(self):
        """Test that messages are allowed under the limit."""
        user_id = uuid4()

        # Should allow up to 100 messages per hour
        for _ in range(100):
            assert rate_limiter.check_message_rate(user_id) is True
            rate_limiter.record_message(user_id)

    def test_message_rate_blocks_over_limit(self):
        """Test that messages are blocked over the limit."""
        user_id = uuid4()

        # Use up the limit
        for _ in range(100):
            rate_limiter.record_message(user_id)

        # Next message should be blocked
        assert rate_limiter.check_message_rate(user_id) is False

    def test_message_rate_separate_per_user(self):
        """Test that rate limits are separate per user."""
        user1 = uuid4()
        user2 = uuid4()

        # User 1 uses up their limit
        for _ in range(100):
            rate_limiter.record_message(user1)

        # User 2 should still be able to send
        assert rate_limiter.check_message_rate(user2) is True

    def test_get_message_remaining(self):
        """Test getting remaining message count."""
        user_id = uuid4()

        assert rate_limiter.get_message_remaining(user_id) == 100

        rate_limiter.record_message(user_id)
        rate_limiter.record_message(user_id)

        assert rate_limiter.get_message_remaining(user_id) == 98

    def test_get_concurrent_sessions_remaining(self):
        """Test getting remaining session slots."""
        user_id = uuid4()

        assert rate_limiter.get_concurrent_sessions_remaining(user_id) == 100

        rate_limiter.record_session_started(user_id)
        rate_limiter.record_session_started(user_id)

        assert rate_limiter.get_concurrent_sessions_remaining(user_id) == 98

    def test_get_limits_info(self):
        """Test getting full limits info."""
        user_id = uuid4()

        rate_limiter.record_session_started(user_id)
        rate_limiter.record_session_started(user_id)
        rate_limiter.record_message(user_id)

        info = rate_limiter.get_limits_info(user_id)

        assert info["user_id"] == str(user_id)
        assert info["concurrent_sessions"]["active"] == 2
        assert info["concurrent_sessions"]["max"] == 100
        assert info["concurrent_sessions"]["remaining"] == 98
        assert info["message_rate"]["remaining"] == 99
        assert info["message_rate"]["max_per_hour"] == 100

    def test_rate_limit_reset(self):
        """Test that reset clears all state."""
        user_id = uuid4()

        rate_limiter.record_session_started(user_id)
        rate_limiter.record_message(user_id)

        rate_limiter.reset()

        assert rate_limiter.get_active_sessions(user_id) == 0
        assert rate_limiter.get_message_remaining(user_id) == 100

    def test_max_constants(self):
        """Test that max constants are correct."""
        assert RateLimiter.MAX_CONCURRENT_SESSIONS == 100
        assert RateLimiter.MESSAGES_PER_HOUR == 100
        assert RateLimiter.WINDOW_SIZE_SECONDS == 3600
