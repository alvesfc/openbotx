"""Orchestrator for OpenBotX - main processing loop."""

import asyncio
import time
from typing import Any

from openbotx.agent.brain import AgentBrain, get_agent_brain
from openbotx.core.attachments import AttachmentProcessor, get_attachment_processor
from openbotx.core.context_store import ContextStore, get_context_store
from openbotx.core.message_bus import MessageBus, get_message_bus
from openbotx.core.security import SecurityManager, get_security_manager
from openbotx.core.skills_registry import SkillsRegistry, get_skills_registry
from openbotx.core.telemetry import Telemetry, get_telemetry
from openbotx.core.tools_registry import ToolsRegistry, get_tools_registry
from openbotx.helpers.logger import get_logger
from openbotx.helpers.tokens import count_tokens, estimate_tokens
from openbotx.models.enums import GatewayType, ProviderType, ResponseCapability
from openbotx.models.message import (
    InboundMessage,
    MessageContext,
    OutboundMessage,
    ProcessingResult,
)
from openbotx.providers.base import get_provider_registry
from openbotx.providers.gateway.base import GatewayProvider


class Orchestrator:
    """Orchestrates message processing pipeline."""

    def __init__(
        self,
        message_bus: MessageBus | None = None,
        context_store: ContextStore | None = None,
        skills_registry: SkillsRegistry | None = None,
        tools_registry: ToolsRegistry | None = None,
        security_manager: SecurityManager | None = None,
        telemetry: Telemetry | None = None,
        attachment_processor: AttachmentProcessor | None = None,
        agent_brain: AgentBrain | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            message_bus: Message bus instance
            context_store: Context store instance
            skills_registry: Skills registry instance
            tools_registry: Tools registry instance
            security_manager: Security manager instance
            telemetry: Telemetry instance
            attachment_processor: Attachment processor instance
            agent_brain: Agent brain instance
        """
        self._message_bus = message_bus or get_message_bus()
        self._context_store = context_store or get_context_store()
        self._skills_registry = skills_registry or get_skills_registry()
        self._tools_registry = tools_registry or get_tools_registry()
        self._security_manager = security_manager or get_security_manager()
        self._telemetry = telemetry or get_telemetry()
        self._attachment_processor = attachment_processor or get_attachment_processor()
        self._agent_brain = agent_brain or get_agent_brain()

        self._logger = get_logger("orchestrator")
        self._running = False
        self._process_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        """Initialize the orchestrator and all components."""
        self._logger.info("initializing_orchestrator")

        # Load skills
        skill_count = await self._skills_registry.load_skills()
        self._logger.info("skills_loaded", count=skill_count)

        # Load tools
        tool_count = await self._tools_registry.load_tools()
        self._logger.info("tools_loaded", count=tool_count)

        # Initialize agent brain
        self._agent_brain._skills_registry = self._skills_registry
        self._agent_brain._tools_registry = self._tools_registry
        await self._agent_brain.initialize()

        # Set up message handler
        self._message_bus.add_handler(self._handle_message)

        self._logger.info("orchestrator_initialized")

    async def start(self) -> None:
        """Start the orchestrator processing loop."""
        if self._running:
            return

        self._running = True
        await self._message_bus.start()
        self._process_task = asyncio.create_task(self._process_loop())

        self._logger.info("orchestrator_started")

    async def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        await self._message_bus.stop()
        self._logger.info("orchestrator_stopped")

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                await self._message_bus.process_one()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("process_loop_error", error=str(e))
                await asyncio.sleep(0.1)

    async def _handle_message(self, message: InboundMessage) -> None:
        """Handle a message from the queue.

        Args:
            message: Inbound message to process
        """
        metrics = self._telemetry.start_operation(
            "message_processing",
            message.correlation_id,
            message_id=message.id,
            channel_id=message.channel_id,
            gateway=message.gateway.value,
        )

        try:
            result = await self.process_message(message)

            # Send response if gateway supports it
            if result.response:
                await self._send_response(result.response)

            self._telemetry.end_operation(metrics, success=result.success)

        except Exception as e:
            self._logger.error(
                "message_handling_error",
                message_id=message.id,
                error=str(e),
            )
            self._telemetry.end_operation(metrics, success=False, error=str(e))

    async def process_message(self, message: InboundMessage) -> ProcessingResult:
        """Process a single message.

        Args:
            message: Message to process

        Returns:
            Processing result
        """
        start_time = time.time()
        tools_called = []
        skills_used = []

        self._logger.info(
            "processing_message",
            message_id=message.id,
            correlation_id=message.correlation_id,
            channel_id=message.channel_id,
        )

        # Step 1: Process attachments (transcribe audio, etc.)
        if message.has_attachments:
            message = await self._attachment_processor.process_message_attachments(message)

        # Step 2: Security check
        if message.text:
            is_valid, violation = self._security_manager.validate_message(
                message.text,
                channel_id=message.channel_id,
                user_id=message.user_id,
            )

            if not is_valid:
                self._logger.warning(
                    "message_rejected",
                    message_id=message.id,
                    violation=(violation.violation_type.value if violation else "unknown"),
                )
                # Create rejection response
                from openbotx.models.response import AgentResponse

                rejection_response = AgentResponse()
                rejection_response.add_error(self._security_manager.rejection_message)

                gateway_capabilities = self._get_gateway_capabilities(message.gateway)
                outbound = rejection_response.to_outbound_message(
                    channel_id=message.channel_id,
                    gateway_capabilities=gateway_capabilities,
                    gateway_type=message.gateway,
                    reply_to=message.id,
                    correlation_id=message.correlation_id,
                )

                return ProcessingResult(
                    success=False,
                    error=self._security_manager.rejection_message,
                    response=outbound,
                )

        # Step 3: Load context
        context = await self._context_store.load_context(message.channel_id)

        # Step 4: Estimate tokens and check budget
        estimated_tokens = estimate_tokens(message.text or "")
        context_tokens = sum(count_tokens(t.content) for t in context.history[-20:])

        # Step 5: Build message context
        msg_context = MessageContext(
            message=message,
            history=[{"role": t.role, "content": t.content} for t in context.history[-20:]],
            summary=context.summary,
            available_skills=[s.id for s in self._skills_registry.list_skills()],
            available_tools=[t.name for t in self._tools_registry.list_tools()],
            estimated_tokens=estimated_tokens + context_tokens,
        )

        # Step 6: Process with agent
        response = await self._agent_brain.process(message, msg_context)
        skills_used = response.skills_used
        tools_called = response.tools_called

        # Step 7: Handle learning if needed
        if response.needs_learning and response.learning_topic:
            skill = await self._agent_brain.learn_skill(
                response.learning_topic,
                msg_context,
            )
            if skill:
                self._logger.info(
                    "skill_learned_from_message",
                    skill_id=skill.id,
                    topic=response.learning_topic,
                )

        # Step 8: Save to context
        await self._context_store.add_turn(
            message.channel_id,
            "user",
            message.text or "",
        )
        await self._context_store.add_turn(
            message.channel_id,
            "assistant",
            response.text,
        )

        # Step 9: Check if summarization needed
        updated_context = await self._context_store.load_context(message.channel_id)
        if self._context_store.needs_summarization(updated_context):
            # TODO: Trigger summarization in background
            pass

        # Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)

        # Get gateway capabilities
        gateway_capabilities = self._get_gateway_capabilities(message.gateway)

        # Build response based on gateway capabilities
        outbound = response.to_outbound_message(
            channel_id=message.channel_id,
            gateway_capabilities=gateway_capabilities,
            gateway_type=message.gateway,
            reply_to=message.id,
            correlation_id=message.correlation_id,
        )

        return ProcessingResult(
            success=True,
            response=outbound,
            tools_called=tools_called,
            skills_used=skills_used,
            processing_time_ms=processing_time,
        )

    def _get_gateway_capabilities(self, gateway_type: GatewayType) -> set[ResponseCapability]:
        """Get capabilities of a specific gateway.

        Args:
            gateway_type: Gateway type to check

        Returns:
            Set of response capabilities
        """
        registry = get_provider_registry()
        gateways = registry.get_all(ProviderType.GATEWAY)

        for gateway in gateways:
            if isinstance(gateway, GatewayProvider):
                if gateway.gateway_type == gateway_type:
                    return gateway.response_capabilities

        # Default: text only
        return {ResponseCapability.TEXT}

    async def _send_response(self, response: OutboundMessage) -> bool:
        """Send a response via the appropriate gateway.

        Args:
            response: Response to send

        Returns:
            True if sent successfully
        """
        registry = get_provider_registry()
        gateways = registry.get_all(ProviderType.GATEWAY)

        for gateway in gateways:
            if isinstance(gateway, GatewayProvider):
                if gateway.gateway_type.value == response.gateway.value:
                    if gateway.supports_response_type(response.response_type):
                        try:
                            return await gateway.send(response)
                        except Exception as e:
                            self._logger.error(
                                "send_response_error",
                                gateway=gateway.name,
                                error=str(e),
                            )

        self._logger.warning(
            "no_gateway_for_response",
            gateway=response.gateway.value,
        )
        return False

    def enqueue_message(self, message: InboundMessage) -> str:
        """Enqueue a message for processing.

        Args:
            message: Message to enqueue

        Returns:
            Message ID
        """
        return self._message_bus.enqueue(message)

    @property
    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._running

    @property
    def stats(self) -> dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            "running": self._running,
            "queue": self._message_bus.stats,
            "telemetry": self._telemetry.get_stats(),
            "skills_count": self._skills_registry.skill_count,
            "tools_count": self._tools_registry.tool_count,
        }


# Global orchestrator instance
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """Get the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def set_orchestrator(orchestrator: Orchestrator) -> None:
    """Set the global orchestrator instance."""
    global _orchestrator
    _orchestrator = orchestrator
