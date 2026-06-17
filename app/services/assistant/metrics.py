"""
Per-session telemetry metrics for the Assistant.

Provides counters for:
- assistant_sessions_created: Total sessions created
- assistant_tool_calls_total{tool}: Tool calls by tool name
- assistant_llm_tokens_total{role}: LLM tokens by role (system/user/assistant)
- assistant_steps_total{status}: Steps by final status

The counters are process-local (suitable for single-instance deployment).
For multi-instance, expose via /metrics endpoint for Prometheus scraping.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

logger: threading.Lock = threading.Lock()


@dataclass
class SessionMetrics:
    """
    Metrics collected during a single session.
    
    Attributes:
        session_id: The session UUID.
        user_id: The user UUID.
        start_time: Unix timestamp when session started.
        end_time: Unix timestamp when session ended (None if running).
        status: Final status ("completed", "cancelled", "failed").
        step_count: Number of steps executed.
        tokens_used: Total tokens consumed (system + user + assistant).
        tool_calls: Counter of tool calls by tool name.
        steps_by_status: Counter of steps by final status.
    """
    session_id: UUID
    user_id: UUID
    start_time: float
    end_time: float | None = None
    status: str = "running"
    step_count: int = 0
    tokens_used: int = 0
    tool_calls: Counter[str] = field(default_factory=Counter)
    steps_by_status: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "session_id": str(self.session_id),
            "user_id": str(self.user_id),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "steps_count": self.step_count,
            "tokens_used": self.tokens_used,
            "tool_calls": dict(self.tool_calls),
            "wall_time": (self.end_time - self.start_time) if self.end_time else None,
        }


class AssistantMetrics:
    """
    Global metrics registry for the Assistant.
    
    Tracks:
    - Total sessions created
    - Tool calls by tool name
    - LLM tokens by role
    - Steps by final status
    - Active sessions per user
    """
    
    _instance: AssistantMetrics | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> AssistantMetrics:
        """Singleton pattern for process-local metrics."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Initialize all counters."""
        self._sessions_created: int = 0
        self._tool_calls: Counter[str] = Counter()
        self._tokens_by_role: Counter[str] = Counter()
        self._steps_by_status: Counter[str] = Counter()
        self._active_sessions: dict[str, int] = {}  # user_id -> count
        self._session_metrics: dict[str, SessionMetrics] = {}  # session_id -> metrics
    
    def reset(self) -> None:
        """Reset all metrics (for testing only)."""
        with self._lock:
            self._initialize()
    
    @property
    def sessions_created(self) -> int:
        """Total number of assistant sessions created."""
        return self._sessions_created
    
    def record_session_created(self, session_id: UUID, user_id: UUID) -> SessionMetrics:
        """
        Record that a new session was created.
        
        Args:
            session_id: The new session ID.
            user_id: The user ID who created the session.
            
        Returns:
            SessionMetrics object for this session.
        """
        import time
        
        with self._lock:
            self._sessions_created += 1
            
            # Track active sessions per user
            user_id_str = str(user_id)
            self._active_sessions[user_id_str] = self._active_sessions.get(user_id_str, 0) + 1
            
            # Create session metrics
            metrics = SessionMetrics(
                session_id=session_id,
                user_id=user_id,
                start_time=time.time(),
            )
            self._session_metrics[str(session_id)] = metrics
            
            return metrics
    
    def record_session_ended(
        self,
        session_id: UUID,
        status: str,
        step_count: int,
        tool_calls: Counter[str],
        tokens_used: int,
    ) -> None:
        """
        Record that a session has ended.
        
        Args:
            session_id: The session ID.
            status: Final status ("completed", "cancelled", "failed").
            step_count: Number of steps executed.
            tool_calls: Counter of tool calls by tool name.
            tokens_used: Total tokens consumed.
        """
        import time
        
        with self._lock:
            session_id_str = str(session_id)
            metrics = self._session_metrics.get(session_id_str)
            
            if metrics:
                metrics.end_time = time.time()
                metrics.status = status
                metrics.step_count = step_count
                metrics.tool_calls = tool_calls
                metrics.tokens_used = tokens_used
            else:
                # Create metrics record for sessions not tracked at start
                self._session_metrics[session_id_str] = SessionMetrics(
                    session_id=session_id,
                    user_id=UUID("00000000-0000-0000-0000-000000000000"),  # placeholder
                    start_time=time.time() - 60,  # assume 1 min ago
                    end_time=time.time(),
                    status=status,
                    step_count=step_count,
                    tool_calls=tool_calls,
                    tokens_used=tokens_used,
                )
            
            # Update global counters
            for tool_name, count in tool_calls.items():
                self._tool_calls[tool_name] += count
            
            for step_status, count in Counter({"completed": step_count}).items():
                self._steps_by_status[step_status] += count
    
    def record_tool_call(self, tool_name: str) -> None:
        """
        Record a single tool call.
        
        Args:
            tool_name: The name of the tool called.
        """
        with self._lock:
            self._tool_calls[tool_name] += 1
    
    def record_tokens(self, role: str, count: int) -> None:
        """
        Record LLM token usage.
        
        Args:
            role: The role ("system", "user", "assistant").
            count: Number of tokens used.
        """
        with self._lock:
            self._tokens_by_role[role] += count
    
    def record_step(self, status: str) -> None:
        """
        Record a step completion.
        
        Args:
            status: The step status ("completed", "failed", "skipped").
        """
        with self._lock:
            self._steps_by_status[status] += 1
    
    def get_active_sessions_count(self, user_id: UUID) -> int:
        """
        Get the number of active sessions for a user.
        
        Args:
            user_id: The user ID.
            
        Returns:
            Number of active sessions.
        """
        with self._lock:
            return self._active_sessions.get(str(user_id), 0)
    
    def decrement_active_sessions(self, user_id: UUID) -> None:
        """
        Decrement active sessions count for a user.
        
        Args:
            user_id: The user ID.
        """
        with self._lock:
            user_id_str = str(user_id)
            if user_id_str in self._active_sessions:
                self._active_sessions[user_id_str] = max(0, self._active_sessions[user_id_str] - 1)
    
    def get_session_metrics(self, session_id: UUID) -> SessionMetrics | None:
        """
        Get metrics for a specific session.
        
        Args:
            session_id: The session ID.
            
        Returns:
            SessionMetrics if found, None otherwise.
        """
        with self._lock:
            return self._session_metrics.get(str(session_id))
    
    def get_summary(self) -> dict:
        """
        Get a summary of all metrics.
        
        Returns:
            Dictionary with all metric counters.
        """
        with self._lock:
            return {
                "sessions_created": self._sessions_created,
                "tool_calls_total": dict(self._tool_calls),
                "llm_tokens_total": dict(self._tokens_by_role),
                "steps_total": dict(self._steps_by_status),
                "active_sessions": dict(self._active_sessions),
            }


# Global metrics instance
metrics = AssistantMetrics()
