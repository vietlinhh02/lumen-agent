"""
Planner Agent for the Assistant.

Creates and updates plans based on user messages and project context.
Uses structured output for reliable plan generation.

Usage:
    planner = PlannerAgent(provider=provider, tools=tools)
    async for event in planner.create_plan(message, project_context):
        yield event
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.assistant.events import (
    BaseEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
)
from app.ai.prompts import (
    CREATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    UPDATE_PLAN_PROMPT,
)
from app.ai.structured_outputs import PlanOutput, StepOutput

if TYPE_CHECKING:
    from app.ai.provider import LLMProvider

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Planner agent that creates and updates execution plans.

    The planner takes a user message and project context, then produces a
    structured plan with ordered steps. Each step references a specific
    tool to call.

    The planner yields events as it works:
    1. MessageEvent with reasoning
    2. PlanEvent with the created/updated plan

    Attributes:
        provider: LLM provider for making AI calls.
        tools: List of available tool names for the planner to choose from.
    """

    def __init__(
        self,
        provider: "LLMProvider",
        tools: Optional[List[Any]] = None,
    ) -> None:
        """
        Initialize the planner agent.

        Args:
            provider: LLM provider for making AI calls.
            tools: Optional list of tool objects. If not provided, will use
                   tool names from the default toolkit.
        """
        self.provider = provider
        self._tools = tools or []
        self._tool_names = self._extract_tool_names()

    def _extract_tool_names(self) -> List[str]:
        """Extract tool names from tool objects."""
        names = []
        for tool in self._tools:
            if hasattr(tool, "name"):
                names.append(tool.name)
            elif isinstance(tool, dict) and "name" in tool:
                names.append(tool["name"])
            elif isinstance(tool, str):
                names.append(tool)
        return names

    def _format_tool_list(self) -> str:
        """Format available tools for the prompt."""
        if not self._tool_names:
            return "(No tools available - this is an error)"
        return "\n".join(f"- {name}" for name in self._tool_names)

    def _steps_to_text(self, steps: List[StepOutput]) -> str:
        """Format steps for the update plan prompt."""
        lines = []
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. [{step.id}] {step.description} -> {step.expected_tool}")
        return "\n".join(lines) if lines else "(no steps)"

    async def create_plan(
        self,
        message: str,
        project_context: Dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Create a new plan based on a user message and project context.

        Args:
            message: The user's request/message.
            project_context: Dict with project details:
                - project_id: UUID string (optional)
                - project_name: Project title (optional)
                - topic: Research topic (optional)
                - research_question: Optional research question

        Yields:
            MessageEvent with reasoning about the plan
            PlanEvent with the created plan
        """
        # Build context with defaults if not provided
        project_id = project_context.get("project_id", "no-project")
        project_name = project_context.get("project_name", "General Assistant")
        topic = project_context.get("topic", "general research assistance")
        research_question = project_context.get("research_question", "Not specified")

        # Format the prompt
        tool_list = self._format_tool_list()

        # Yield reasoning message
        reasoning = self._build_reasoning_message(message, project_context)
        yield MessageEvent(
            role="assistant",
            content=reasoning,
        )

        # Build the prompt
        prompt = CREATE_PLAN_PROMPT.format(
            message=message,
            project_id=project_id,
            project_name=project_name,
            topic=topic,
            research_question=research_question,
            tool_list=tool_list,
        )

        # Call the LLM with structured output
        try:
            plan_output = await self._call_llm(prompt)
        except Exception as exc:
            logger.error("Plan creation failed: %s", exc)
            yield MessageEvent(
                role="assistant",
                content=f"Failed to create plan: {exc}",
            )
            return

        # Convert to PlanEvent
        plan_id = str(uuid.uuid4())
        steps = [
            PlanStep(
                id=step.id,
                description=step.description,
                expected_tool=step.expected_tool,
                status="pending",
            )
            for step in plan_output.steps
        ]

        yield PlanEvent(
            plan_id=plan_id,
            title=plan_output.title,
            language=plan_output.language,
            steps=steps,
        )

    async def update_plan(
        self,
        current_plan: PlanEvent,
        last_step_id: str,
        step_result: Dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Update a plan after a step completes.

        This method checks if the plan needs updating based on the step result.
        If the plan is already complete or no update is needed, it yields the
        same plan.

        Args:
            current_plan: The current plan event.
            last_step_id: The ID of the step that just completed.
            step_result: The result dict from the step execution.

        Yields:
            MessageEvent with reasoning about the update
            PlanEvent with the (possibly updated) plan
        """
        # Check if plan is already complete
        remaining_steps = [s for s in current_plan.steps if s.status == "pending"]
        if not remaining_steps:
            yield MessageEvent(
                role="assistant",
                content="Plan already complete. No update needed.",
            )
            yield current_plan
            return

        # Find the completed step
        completed_step = None
        for step in current_plan.steps:
            if step.id == last_step_id:
                completed_step = step
                break

        if completed_step is None:
            logger.warning("Step %s not found in plan", last_step_id)
            yield current_plan
            return

        # Format current plan for prompt
        plan_text = self._steps_to_text([
            StepOutput(id=s.id, description=s.description, expected_tool=s.expected_tool)
            for s in current_plan.steps
        ])

        # Check if step was successful
        step_success = step_result.get("ok", True)
        step_message = step_result.get("message", str(step_result))

        # Build the update prompt
        prompt = UPDATE_PLAN_PROMPT.format(
            current_plan=plan_text,
            step_id=completed_step.id,
            step_description=completed_step.description,
            step_result=f"Success: {step_success} - {step_message}",
        )

        # Yield reasoning
        yield MessageEvent(
            role="assistant",
            content=f"Step '{completed_step.description}' completed. Checking if plan needs updates...",
        )

        # Check if update is needed (simple heuristic first)
        needs_update = False
        update_reason = ""

        # Check if step failed
        if not step_success:
            needs_update = True
            error_code = step_result.get("error_code", "UNKNOWN")
            update_reason = f"Step failed with error: {error_code}"

        # For now, we'll skip LLM call for simple cases and only use it
        # when there's an actual failure or we need complex reasoning
        if needs_update:
            # Mark remaining steps as potentially affected
            steps = []
            for step in current_plan.steps:
                if step.id == last_step_id:
                    steps.append(PlanStep(
                        id=step.id,
                        description=step.description,
                        expected_tool=step.expected_tool,
                        status="failed" if not step_success else "completed",
                    ))
                elif step.status == "pending":
                    # Mark pending steps as skipped if previous step failed
                    steps.append(PlanStep(
                        id=step.id,
                        description=step.description,
                        expected_tool=step.expected_tool,
                        status="pending",  # Keep as pending, but context is lost
                    ))
                else:
                    steps.append(step)

            yield MessageEvent(
                role="assistant",
                content=update_reason + " Remaining steps may need review.",
            )

            yield PlanEvent(
                plan_id=current_plan.plan_id,
                title=current_plan.title,
                language=current_plan.language,
                steps=steps,
            )
        else:
            # No update needed - yield the current plan with completed step marked
            steps = []
            for step in current_plan.steps:
                if step.id == last_step_id:
                    steps.append(PlanStep(
                        id=step.id,
                        description=step.description,
                        expected_tool=step.expected_tool,
                        status="completed",
                    ))
                else:
                    steps.append(step)

            yield MessageEvent(
                role="assistant",
                content="Plan continues as expected.",
            )

            yield PlanEvent(
                plan_id=current_plan.plan_id,
                title=current_plan.title,
                language=current_plan.language,
                steps=steps,
            )

    def _build_reasoning_message(
        self,
        message: str,
        project_context: Dict[str, Any],
    ) -> str:
        """Build a reasoning message explaining the plan approach."""
        topic = project_context.get("topic", "")
        return (
            f"Analyzing request about '{topic}'...\n\n"
            f"Breaking down the task into actionable steps. "
            f"Each step will use an appropriate tool to progress toward the goal."
        )

    async def _call_llm(self, prompt: str) -> PlanOutput:
        """
        Call the LLM to generate a plan.

        Args:
            prompt: The formatted prompt for plan creation.

        Returns:
            PlanOutput with the generated plan.

        Raises:
            Exception: If the LLM call fails.
        """
        # Build messages for the provider
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        # Call the provider with structured output
        response = await self.provider.complete_structured(
            messages=messages,
            schema=PlanOutput.model_json_schema(),
            tool_name="plan_output",
        )

        # Parse response into PlanOutput
        plan_output = PlanOutput.model_validate(response)

        # Validate steps have unique IDs
        step_ids = [step.id for step in plan_output.steps]
        if len(step_ids) != len(set(step_ids)):
            # Ensure unique IDs
            for i, step in enumerate(plan_output.steps):
                step.id = f"step_{i + 1}"

        return plan_output
