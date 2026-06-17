"""
PlanActFlow - State machine that orchestrates planner and executor agents.

This flow implements the Plan-Act pattern:
1. PLANNING: Create a plan from user message
2. EXECUTING: Execute each step in the plan
3. UPDATING: Update plan after each step
4. SUMMARIZING: Generate final summary
5. COMPLETED: Done

Supports resume from EXECUTING after WaitEvent and enforces hard limits
on steps, tokens, and wall time.

Usage:
    flow = PlanActFlow(
        planner=planner_agent,
        executor=execution_agent,
        tools=tools,
    )
    async for event in flow.run(message):
        yield event
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.assistant.events import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    StepEvent,
    ToolEvent,
    WaitEvent,
)

if TYPE_CHECKING:
    from app.agents.assistant.agents.execution import ExecutionAgent
    from app.agents.assistant.agents.planner import PlannerAgent

logger = logging.getLogger(__name__)


class FlowState(Enum):
    """States in the PlanActFlow state machine."""
    
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    UPDATING = "updating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    WAITING = "waiting"  # Special state for WaitEvent


class FlowErrorCode(Enum):
    """Error codes for flow-level errors."""
    
    MAX_STEPS_REACHED = "MAX_STEPS_REACHED"
    MAX_TOKENS_REACHED = "MAX_TOKENS_REACHED"
    MAX_WALL_TIME_REACHED = "MAX_WALL_TIME_REACHED"
    CANCELLED = "CANCELLED"
    PLANNING_FAILED = "PLANNING_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


# Default limits
DEFAULT_MAX_STEPS = 20
DEFAULT_MAX_TOKENS = 200_000
DEFAULT_MAX_WALL_TIME_SECONDS = 600  # 10 minutes


class PlanActFlow:
    """
    Plan-Act state machine that orchestrates planner and executor agents.
    
    The flow walks through these states:
    - IDLE: Initial state
    - PLANNING: Create a plan using the planner agent
    - EXECUTING: Execute each pending step using the executor agent
    - UPDATING: Update the plan after each step completes
    - SUMMARIZING: Generate final summary
    - COMPLETED: Flow is done
    - WAITING: Special state when waiting for user input (after WaitEvent)
    
    Attributes:
        planner: PlannerAgent instance for creating/updating plans.
        executor: ExecutionAgent instance for executing steps.
        max_steps: Maximum number of steps to execute.
        max_total_tokens: Maximum total tokens to use.
        max_wall_time_seconds: Maximum wall time in seconds.
    """

    def __init__(
        self,
        planner: "PlannerAgent",
        executor: "ExecutionAgent",
        max_steps: int = DEFAULT_MAX_STEPS,
        max_total_tokens: int = DEFAULT_MAX_TOKENS,
        max_wall_time_seconds: int = DEFAULT_MAX_WALL_TIME_SECONDS,
        project_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the PlanActFlow.

        Args:
            planner: PlannerAgent instance.
            executor: ExecutionAgent instance.
            max_steps: Maximum steps to execute (default: 20).
            max_total_tokens: Maximum tokens allowed (default: 200,000).
            max_wall_time_seconds: Maximum wall time in seconds (default: 600).
            project_context: Optional project context for the flow.
        """
        self.planner = planner
        self.executor = executor
        
        # Limits
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.max_wall_time_seconds = max_wall_time_seconds
        
        # Project context
        self.project_context = project_context or {}
        
        # State tracking
        self._state = FlowState.IDLE
        self._current_plan: Optional[PlanEvent] = None
        self._current_step_index: int = 0
        self._step_count: int = 0
        self._total_tokens_used: int = 0
        self._start_time: Optional[datetime] = None
        
        # Waiting state tracking
        self._waiting_for_user: bool = False
        self._waiting_step_id: Optional[str] = None
        
        # Cancellation flag
        self._cancelled = False

    @property
    def state(self) -> FlowState:
        """Get the current state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if the flow is currently running."""
        return self._state not in {
            FlowState.IDLE,
            FlowState.COMPLETED,
        }

    @property
    def is_waiting(self) -> bool:
        """Check if the flow is waiting for user input."""
        return self._waiting_for_user

    @property
    def stats(self) -> Dict[str, Any]:
        """Get flow statistics."""
        wall_time = 0
        if self._start_time:
            wall_time = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        
        return {
            "state": self._state.value,
            "step_count": self._step_count,
            "total_tokens": self._total_tokens_used,
            "wall_time_seconds": wall_time,
            "is_waiting": self._waiting_for_user,
            "current_step_index": self._current_step_index,
        }

    def cancel(self) -> None:
        """Cancel the flow execution."""
        logger.info("Flow cancellation requested")
        self._cancelled = True

    async def run(
        self,
        message: str,
        resume: bool = False,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Run the Plan-Act flow.

        Args:
            message: The user's message/request.
            resume: If True, resume from waiting state.

        Yields:
            BaseEvent: Events from the flow execution.

        Raises:
            CancelledError: If the flow is cancelled.
        """
        # Check for cancellation at start
        if self._cancelled:
            yield ErrorEvent(
                code=FlowErrorCode.CANCELLED.value,
                message="Flow was cancelled before starting",
            )
            yield DoneEvent(summary="Flow cancelled.")
            return

        # Start timing
        self._start_time = datetime.now(timezone.utc)

        # Check if resuming from waiting state
        if resume and self._waiting_for_user:
            async for event in self._handle_resume(message):
                yield event
            return

        # Emit state transition to PLANNING
        self._state = FlowState.PLANNING
        logger.info("Flow state transition: IDLE -> PLANNING")

        # ── PLANNING STATE ──────────────────────────────────────────────────────
        try:
            async for event in self._run_planning(message):
                yield event
                if isinstance(event, ErrorEvent):
                    return
                if isinstance(event, WaitEvent):
                    self._waiting_for_user = True
                    self._state = FlowState.WAITING
                    return
        except asyncio.CancelledError:
            async for event in self._handle_cancellation():
                yield event
            return
        except Exception as exc:
            logger.error("Planning failed: %s", exc)
            yield ErrorEvent(
                code=FlowErrorCode.PLANNING_FAILED.value,
                message=f"Failed to create plan: {exc}",
            )
            yield DoneEvent(summary="Flow failed during planning.")
            return

        # Check cancellation after planning
        if self._cancelled:
            async for event in self._handle_cancellation():
                yield event
            return

        # ── EXECUTING STATE ──────────────────────────────────────────────────────
        self._state = FlowState.EXECUTING
        logger.info("Flow state transition: PLANNING -> EXECUTING")

        try:
            async for event in self._run_execution(message):
                yield event
        except asyncio.CancelledError:
            async for event in self._handle_cancellation():
                yield event
            return

        # ── COMPLETED STATE ──────────────────────────────────────────────────────
        self._state = FlowState.COMPLETED
        logger.info("Flow state transition: ... -> COMPLETED")

        yield DoneEvent(summary=self._build_summary())

    async def _run_planning(self, message: str) -> AsyncGenerator[BaseEvent, None]:
        """Run the planning phase."""
        # Create plan using the planner
        async for event in self.planner.create_plan(
            message=message,
            project_context=self.project_context,
        ):
            # Track token usage (estimate)
            self._total_tokens_used += self._estimate_tokens(event)
            self._check_limits()
            
            yield event
            
            # Capture the plan when we see it
            if isinstance(event, PlanEvent):
                self._current_plan = event

    async def _run_execution(
        self,
        message: str,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run the execution phase for all steps."""
        if self._current_plan is None:
            yield ErrorEvent(
                code=FlowErrorCode.EXECUTION_FAILED.value,
                message="No plan available for execution",
            )
            return

        # Get pending steps
        pending_steps = [
            step for step in self._current_plan.steps
            if step.status == "pending"
        ]

        for step in pending_steps:
            # Check limits at the start of each step
            self._check_limits()
            
            if self._cancelled:
                return

            self._current_step_index += 1
            self._step_count += 1

            # ── EXECUTING step ───────────────────────────────────────────────────
            step_completed = False
            step_result: Dict[str, Any] = {}

            async for event in self.executor.execute_step(
                plan=self._current_plan,
                step=step,
                message=message,
            ):
                # Track token usage
                self._total_tokens_used += self._estimate_tokens(event)
                self._check_limits()
                
                yield event

                # Capture step completion and results
                if isinstance(event, WaitEvent):
                    self._waiting_for_user = True
                    self._waiting_step_id = step.id
                    # Update step status to pending (waiting)
                    self._update_step_status(step.id, "pending")
                    return  # Exit execution, wait for user

                if isinstance(event, ToolEvent) and event.status == "called":
                    step_result = event.result or {}

                if isinstance(event, StepEvent) and event.status == "completed":
                    step_completed = True
                    self._update_step_status(step.id, "completed")

                if isinstance(event, StepEvent) and event.status == "failed":
                    step_completed = True
                    self._update_step_status(step.id, "failed")
                    yield MessageEvent(
                        role="assistant",
                        content=f"Step '{step.description}' failed. Attempting to continue...",
                    )

            # ── UPDATING state ─────────────────────────────────────────────────
            if step_completed:
                self._state = FlowState.UPDATING
                logger.info("Flow state transition: EXECUTING -> UPDATING")

                # Update the plan
                async for event in self.planner.update_plan(
                    current_plan=self._current_plan,
                    last_step_id=step.id,
                    step_result=step_result,
                ):
                    self._total_tokens_used += self._estimate_tokens(event)
                    self._check_limits()
                    
                    yield event

                    # Capture updated plan
                    if isinstance(event, PlanEvent):
                        self._current_plan = event

                # Back to executing for next step
                self._state = FlowState.EXECUTING

        # ── SUMMARIZING state ──────────────────────────────────────────────────
        self._state = FlowState.SUMMARIZING
        logger.info("Flow state transition: EXECUTING -> SUMMARIZING")

        yield MessageEvent(
            role="assistant",
            content=self._build_summary(),
        )

    async def _handle_resume(
        self,
        message: str,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Handle resuming from a waiting state."""
        logger.info("Resuming flow from waiting state")
        
        self._waiting_for_user = False
        self._state = FlowState.EXECUTING

        if self._current_plan is None or self._waiting_step_id is None:
            yield ErrorEvent(
                code=FlowErrorCode.EXECUTION_FAILED.value,
                message="Cannot resume: no plan or step context",
            )
            yield DoneEvent(summary="Flow failed to resume.")
            return

        # Find the waiting step and update its status
        waiting_step = None
        for step in self._current_plan.steps:
            if step.id == self._waiting_step_id:
                waiting_step = step
                break

        if waiting_step is None:
            yield ErrorEvent(
                code=FlowErrorCode.EXECUTION_FAILED.value,
                message=f"Cannot resume: step {self._waiting_step_id} not found",
            )
            yield DoneEvent(summary="Flow failed to resume.")
            return

        # Mark step as running again
        self._update_step_status(waiting_step.id, "running")

        yield MessageEvent(
            role="assistant",
            content=f"Continuing from step '{waiting_step.description}'...",
        )

        # Continue execution
        try:
            async for event in self.executor.execute_step(
                plan=self._current_plan,
                step=waiting_step,
                message=message,  # User's response
            ):
                self._total_tokens_used += self._estimate_tokens(event)
                self._check_limits()
                
                yield event

                # Handle nested WaitEvent (shouldn't happen normally)
                if isinstance(event, WaitEvent):
                    self._waiting_for_user = True
                    self._waiting_step_id = waiting_step.id
                    return

                # Update step status
                if isinstance(event, StepEvent) and event.status == "completed":
                    self._update_step_status(waiting_step.id, "completed")

                if isinstance(event, StepEvent) and event.status == "failed":
                    self._update_step_status(waiting_step.id, "failed")

            # Update the plan
            self._state = FlowState.UPDATING
            async for event in self.planner.update_plan(
                current_plan=self._current_plan,
                last_step_id=waiting_step.id,
                step_result={"ok": True, "message": "User responded"},
            ):
                self._total_tokens_used += self._estimate_tokens(event)
                self._check_limits()
                
                yield event

                if isinstance(event, PlanEvent):
                    self._current_plan = event

            # Continue with remaining steps
            self._state = FlowState.EXECUTING
            
            # Get remaining pending steps (excluding the one we just completed)
            remaining_steps = [
                step for step in self._current_plan.steps
                if step.status == "pending"
            ]

            for step in remaining_steps:
                self._check_limits()
                if self._cancelled:
                    return

                self._current_step_index += 1
                self._step_count += 1

                step_completed = False
                step_result: Dict[str, Any] = {}

                async for event in self.executor.execute_step(
                    plan=self._current_plan,
                    step=step,
                    message=message,
                ):
                    self._total_tokens_used += self._estimate_tokens(event)
                    self._check_limits()
                    
                    yield event

                    if isinstance(event, WaitEvent):
                        self._waiting_for_user = True
                        self._waiting_step_id = step.id
                        self._update_step_status(step.id, "pending")
                        return

                    if isinstance(event, ToolEvent) and event.status == "called":
                        step_result = event.result or {}

                    if isinstance(event, StepEvent) and event.status == "completed":
                        step_completed = True
                        self._update_step_status(step.id, "completed")

                    if isinstance(event, StepEvent) and event.status == "failed":
                        step_completed = True
                        self._update_step_status(step.id, "failed")

                if step_completed:
                    self._state = FlowState.UPDATING
                    async for event in self.planner.update_plan(
                        current_plan=self._current_plan,
                        last_step_id=step.id,
                        step_result=step_result,
                    ):
                        self._total_tokens_used += self._estimate_tokens(event)
                        self._check_limits()
                        
                        yield event

                        if isinstance(event, PlanEvent):
                            self._current_plan = event

                    self._state = FlowState.EXECUTING

            # Summarize
            self._state = FlowState.SUMMARIZING
            yield MessageEvent(
                role="assistant",
                content=self._build_summary(),
            )

            self._state = FlowState.COMPLETED
            yield DoneEvent(summary=self._build_summary())

        except asyncio.CancelledError:
            async for event in self._handle_cancellation():
                yield event
        except Exception as exc:
            logger.error("Resume execution failed: %s", exc)
            yield ErrorEvent(
                code=FlowErrorCode.EXECUTION_FAILED.value,
                message=f"Failed to resume execution: {exc}",
            )
            yield DoneEvent(summary="Flow failed during resume.")

    async def _handle_cancellation(self) -> AsyncGenerator[BaseEvent, None]:
        """Handle flow cancellation."""
        logger.info("Handling flow cancellation")
        
        yield ErrorEvent(
            code=FlowErrorCode.CANCELLED.value,
            message="Flow execution was cancelled",
        )
        yield DoneEvent(summary="Flow cancelled by user.")

    def _check_limits(self) -> None:
        """Check if any limit has been exceeded and raise if so."""
        # Check step count
        if self._step_count >= self.max_steps:
            raise asyncio.CancelledError(
                f"Maximum steps ({self.max_steps}) exceeded"
            )

        # Check token count
        if self._total_tokens_used >= self.max_total_tokens:
            raise asyncio.CancelledError(
                f"Maximum tokens ({self.max_total_tokens}) exceeded"
            )

        # Check wall time
        if self._start_time:
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            if elapsed >= self.max_wall_time_seconds:
                raise asyncio.CancelledError(
                    f"Maximum wall time ({self.max_wall_time_seconds}s) exceeded"
                )

    def _estimate_tokens(self, event: BaseEvent) -> int:
        """Estimate token count for an event (rough approximation)."""
        # Rough estimate: 1 token ≈ 4 characters
        if isinstance(event, MessageEvent):
            return len(event.content) // 4
        elif isinstance(event, PlanEvent):
            content = event.title + "".join(s.description for s in event.steps)
            return len(content) // 4
        elif isinstance(event, ToolEvent):
            args_str = str(event.args) if event.args else ""
            result_str = str(event.result) if event.result else ""
            return (len(args_str) + len(result_str)) // 4
        else:
            return 10  # Small overhead for other events

    def _update_step_status(
        self,
        step_id: str,
        status: str,
    ) -> None:
        """Update the status of a step in the current plan."""
        if self._current_plan is None:
            return

        steps = []
        for step in self._current_plan.steps:
            if step.id == step_id:
                steps.append(PlanStep(
                    id=step.id,
                    description=step.description,
                    expected_tool=step.expected_tool,
                    status=status,
                ))
            else:
                steps.append(step)

        self._current_plan = PlanEvent(
            plan_id=self._current_plan.plan_id,
            title=self._current_plan.title,
            language=self._current_plan.language,
            steps=steps,
        )

    def _build_summary(self) -> str:
        """Build a summary of the flow execution."""
        completed_steps = 0
        failed_steps = 0
        if self._current_plan:
            for step in self._current_plan.steps:
                if step.status == "completed":
                    completed_steps += 1
                elif step.status == "failed":
                    failed_steps += 1

        wall_time = 0
        if self._start_time:
            wall_time = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        summary = (
            f"Flow completed. "
            f"Steps: {completed_steps} completed, {failed_steps} failed. "
            f"Total steps: {self._step_count}/{self.max_steps}. "
            f"Tokens used: ~{self._total_tokens_used}. "
            f"Wall time: {wall_time:.1f}s."
        )
        
        return summary


class BaseFlow:
    """
    Abstract base class for flow implementations.
    
    This class defines the interface that all flow implementations
    should follow. Subclasses must implement the `run` method.
    """
    
    def __init__(
        self,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_total_tokens: int = DEFAULT_MAX_TOKENS,
        max_wall_time_seconds: int = DEFAULT_MAX_WALL_TIME_SECONDS,
    ) -> None:
        """
        Initialize the base flow.
        
        Args:
            max_steps: Maximum steps to execute.
            max_total_tokens: Maximum tokens allowed.
            max_wall_time_seconds: Maximum wall time in seconds.
        """
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.max_wall_time_seconds = max_wall_time_seconds

    async def run(
        self,
        message: str,
        **kwargs,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Run the flow (must be implemented by subclass).

        Args:
            message: Input message.
            **kwargs: Additional arguments.

        Yields:
            BaseEvent: Events from the flow.
        """
        # Using yield instead of return for async generator
        if False:
            yield  # Make this an async generator
