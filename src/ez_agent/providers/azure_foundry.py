"""Azure AI Foundry provider implementation using the Azure AI Agents SDK.

This provider uses the azure-ai-agents package which works with ANY model
deployed in Azure AI Foundry, not just OpenAI models. It supports:
- Azure OpenAI models
- Microsoft models (Phi, etc.)
- Third-party models (Mistral, Llama, etc.)
- Any model connected to your Foundry project

The Agents SDK provides a thread/run pattern with built-in tool handling,
streaming, and proper async support.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from ez_agent.config.models import AuthMethod, ConfigurationSettings, ProviderType
from ez_agent.providers.base import (
    IProvider,
    MessageRole,
    ProviderAuthError,
    ProviderError,
    ProviderMessage,
    ProviderResponse,
    StreamChunk,
    ToolCall,
)
from ez_agent.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


def _lazy_import_azure():
    """Lazily import Azure SDK modules."""
    try:
        from azure.ai.agents import AgentsClient
        from azure.ai.agents.models import (
            ConnectedAgentTool,
            FunctionTool,
            ListSortOrder,
            McpTool,
            MessageDeltaChunk,
            MessageRole as AgentMessageRole,
            RequiredMcpToolCall,
            RunStatus,
            SubmitToolApprovalAction,
            ThreadMessage,
            ThreadRun,
            ToolApproval,
            ToolOutput,
            ToolSet,
        )
        from azure.identity import (
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )
        
        return {
            "AgentsClient": AgentsClient,
            "ConnectedAgentTool": ConnectedAgentTool,
            "FunctionTool": FunctionTool,
            "ListSortOrder": ListSortOrder,
            "McpTool": McpTool,
            "MessageDeltaChunk": MessageDeltaChunk,
            "AgentMessageRole": AgentMessageRole,
            "RequiredMcpToolCall": RequiredMcpToolCall,
            "RunStatus": RunStatus,
            "SubmitToolApprovalAction": SubmitToolApprovalAction,
            "ThreadMessage": ThreadMessage,
            "ThreadRun": ThreadRun,
            "ToolApproval": ToolApproval,
            "ToolOutput": ToolOutput,
            "ToolSet": ToolSet,
            "DefaultAzureCredential": DefaultAzureCredential,
            "ManagedIdentityCredential": ManagedIdentityCredential,
        }
    except ImportError as e:
        raise ImportError(
            "Azure AI SDK not installed. Install with: "
            "pip install azure-ai-agents azure-identity"
        ) from e

@ProviderRegistry.register(ProviderType.AZURE_FOUNDRY)
class AzureFoundryProvider(IProvider):
    """
    Azure AI Foundry provider using the Azure AI Agents SDK.

    This provider works with ANY model deployed in Azure AI Foundry:
    - Azure OpenAI models (GPT-4, GPT-4o, etc.)
    - Microsoft models (Phi-3, Phi-4, etc.)
    - Third-party models (Mistral, Llama, Cohere, etc.)
    
    Uses the Agents/Threads/Runs pattern from azure-ai-agents package.
    
    Supports:
    - DefaultAzureCredential (recommended for development)
    - ManagedIdentityCredential (recommended for production)
    - API key authentication
    """

    def __init__(self, config: ConfigurationSettings):
        """
        Initialize Azure Foundry provider.

        Args:
            config: Configuration settings with Azure-specific options.
        """
        if config.azure is None:
            raise ProviderError(
                "Azure configuration is required for Azure Foundry provider",
                provider="azure_foundry",
            )

        self._config = config.azure
        self._azure = _lazy_import_azure()
        self._tracing_initialized = False
        self._initialize_tracing()  # Initialize tracing before creating client
        self._credential = self._get_credential()
        self._agents_client = self._create_agents_client()
        self._agent_name: str | None = None  # Set by set_agent_name()
        self._agent_instructions: str = "You are a helpful assistant."  # Set by set_instructions()
        self._current_agent = None
        self._current_agent_model = None
        self._persist_agent = self._config.persist_agent
        self._current_mcp_tools: list[Any] = []  # Track MCP tools for run creation
        # A2A tools are now handled locally via A2AToolExecutor (Azure's a2a_preview is broken)
        self._a2a_executor: Any = None  # Lazy initialized A2AToolExecutor

    def _get_a2a_executor(self):
        """Lazily import and initialize the A2A tool executor."""
        if self._a2a_executor is None:
            from ez_agent.providers.a2a_client import A2AToolExecutor
            self._a2a_executor = A2AToolExecutor()
        return self._a2a_executor

    def _initialize_tracing(self) -> None:
        """
        Initialize OpenTelemetry tracing if enabled in configuration.
        
        Supports two modes:
        - Application Insights: Sends traces to Azure Monitor when connection string is provided
        - Console: Prints traces to console when no connection string is provided (for development)
        
        Uses the AIAgentsInstrumentor from azure-ai-agents to automatically trace
        agent operations including agent creation, thread creation, runs, and tool calls.
        """
        tracing_config = self._config.tracing
        
        if not tracing_config.enabled:
            logger.debug("Tracing is disabled")
            return
        
        try:
            # Set environment variable for message content recording
            if tracing_config.capture_message_content:
                import os
                os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"
                logger.info("Message content recording enabled for traces")
            
            # Set service name if provided
            if tracing_config.service_name:
                import os
                os.environ["OTEL_SERVICE_NAME"] = tracing_config.service_name
                logger.info(f"Tracing service name set to: {tracing_config.service_name}")
            
            # Configure Azure tracing
            from azure.core.settings import settings as azure_settings
            azure_settings.tracing_implementation = "opentelemetry"
            
            if tracing_config.application_insights_connection_string:
                # Send traces to Application Insights
                self._setup_application_insights_tracing(
                    tracing_config.application_insights_connection_string,
                    console_tracing=tracing_config.console_tracing,
                )
            else:
                # Console tracing for local development
                self._setup_console_tracing()
            
            # Instrument the Azure AI Agents SDK
            self._instrument_agents_sdk()
            
            self._tracing_initialized = True
            logger.info("OpenTelemetry tracing initialized successfully")
            
        except ImportError as e:
            logger.warning(
                f"Tracing packages not installed. Install with: "
                f"pip install ez-agent[tracing] - Error: {e}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize tracing: {e}")
    
    def _setup_application_insights_tracing(self, connection_string: str, console_tracing: bool = False) -> None:
        """Configure tracing to send to Azure Application Insights."""
        from azure.monitor.opentelemetry import configure_azure_monitor
        
        configure_azure_monitor(connection_string=connection_string)
        logger.info("Tracing configured for Azure Application Insights")
        
        # Optionally also add console output for local debugging
        if console_tracing:
            from opentelemetry import trace
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
            
            tracer_provider = trace.get_tracer_provider()
            if hasattr(tracer_provider, 'add_span_processor'):
                tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                logger.info("Console tracing also enabled (traces go to both App Insights and console)")
    
    def _setup_console_tracing(self) -> None:
        """Configure tracing to output to console for local development."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
        
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(tracer_provider)
        logger.info("Tracing configured for console output (development mode)")
    
    def _instrument_agents_sdk(self) -> None:
        """Instrument the Azure AI Agents SDK for automatic tracing."""
        try:
            from azure.ai.agents.telemetry import AIAgentsInstrumentor
            AIAgentsInstrumentor().instrument()
            logger.debug("AIAgentsInstrumentor activated")
        except ImportError:
            logger.debug("AIAgentsInstrumentor not available, using basic tracing")
        except Exception as e:
            logger.debug(f"Failed to instrument agents SDK: {e}")

    def _get_tracer(self):
        """Get an OpenTelemetry tracer for custom spans."""
        if not self._tracing_initialized:
            return None
        try:
            from opentelemetry import trace
            return trace.get_tracer("ez_agent.providers.azure_foundry")
        except ImportError:
            return None

    def _inject_trace_context(self, headers: dict[str, str]) -> dict[str, str]:
        """
        Inject W3C Trace Context headers into the provided headers dict.
        
        This propagates trace context to MCP tool invocations so they can
        be correlated with the parent trace.
        
        Args:
            headers: Existing headers dict to inject into.
            
        Returns:
            Headers dict with trace context added.
        """
        if not self._tracing_initialized:
            return headers
        
        try:
            from opentelemetry import trace, context
            from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
            
            # Get current span context
            current_span = trace.get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                # Inject trace context using W3C propagator
                propagator = TraceContextTextMapPropagator()
                propagator.inject(headers, context.get_current())
                logger.debug(f"Injected trace context: traceparent={headers.get('traceparent', 'N/A')}")
        except ImportError:
            logger.debug("OpenTelemetry trace propagation not available")
        except Exception as e:
            logger.debug(f"Failed to inject trace context: {e}")
        
        return headers

    def set_agent_name(self, name: str) -> None:
        """
        Set the agent name from the YAML configuration.
        
        The agent will be named 'ez-agent-{name}' in Azure Foundry.
        If an agent with this name already exists, it will be reused.
        
        Args:
            name: The agent name from the YAML configuration.
        """
        self._agent_name = f"ez-agent-{name}"
        logger.info(f"Azure Foundry agent name set to: {self._agent_name}")

    def set_instructions(self, instructions: str) -> None:
        """
        Set the agent instructions from the YAML configuration.
        
        Args:
            instructions: The system instructions for the agent.
        """
        self._agent_instructions = instructions
        logger.debug(f"Azure Foundry agent instructions set ({len(instructions)} chars)")

    def _create_agents_client(self) -> Any:
        """Create the Azure AI Agents client."""
        try:
            # Use the standalone AgentsClient which has the full agents API
            client = self._azure["AgentsClient"](
                endpoint=self._config.endpoint,
                credential=self._credential,
            )
            return client
        except Exception as e:
            raise ProviderError(
                f"Failed to create Azure AI Agents client: {e}",
                provider="azure_foundry",
                cause=e,
            )

    def _get_credential(self) -> Any:
        """Get the appropriate credential based on auth method."""
        if self._config.auth_method == AuthMethod.DEFAULT_CREDENTIAL:
            return self._azure["DefaultAzureCredential"]()
        elif self._config.auth_method == AuthMethod.MANAGED_IDENTITY:
            return self._azure["ManagedIdentityCredential"]()
        elif self._config.auth_method == AuthMethod.API_KEY:
            from azure.core.credentials import AzureKeyCredential
            return AzureKeyCredential(self._config.api_key or "")
        else:
            raise ProviderAuthError(
                f"Unsupported auth method: {self._config.auth_method}",
                provider="azure_foundry",
            )

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "azure_foundry"

    def _find_existing_agent(self, agent_name: str) -> Any | None:
        """Find an existing agent by name."""
        try:
            agents = self._agents_client.list_agents()
            for agent in agents:
                if agent.name == agent_name:
                    logger.info(f"Found existing agent: {agent_name} (ID: {agent.id})")
                    return agent
        except Exception as e:
            logger.debug(f"Error listing agents: {e}")
        return None

    def _get_or_create_agent(self, model: str, tools: list[dict[str, Any]] | None = None) -> Any:
        """Get or create an agent for the specified model."""
        # Use configured name or fallback
        agent_name = self._agent_name or "ez-agent-session"
        
        # Always convert tools to ensure MCP and A2A tools are set up
        all_tool_definitions = []
        self._current_mcp_tools = []  # Reset MCP tools
        
        if tools:
            function_tools, mcp_tools = self._convert_tools_to_agent_format(tools)
            all_tool_definitions.extend(function_tools)
            self._current_mcp_tools = mcp_tools
            
            # Add MCP tool definitions to the agent
            for mcp_tool in mcp_tools:
                logger.info(f"Adding MCP tool definitions: {mcp_tool.definitions}")
                all_tool_definitions.extend(mcp_tool.definitions)
            
            # Note: A2A tools are registered with A2AToolExecutor and added as
            # function tools in _convert_tools_to_agent_format. They are executed
            # locally when the model calls them (Azure's a2a_preview is broken).
        
        a2a_tool_count = len(self._get_a2a_executor().list_tools())
        logger.info(f"Tool definitions for agent: {len(all_tool_definitions)} total, {len(self._current_mcp_tools)} MCP, {a2a_tool_count} A2A (local)")
        
        # Reuse existing agent if model matches
        if self._current_agent and self._current_agent_model == model:
            return self._current_agent

        # Create span for agent initialization using context manager
        tracer = self._get_tracer()
        if tracer:
            from opentelemetry import trace
            with tracer.start_as_current_span(
                "agent_init",
                kind=trace.SpanKind.CLIENT,
            ) as agent_span:
                agent_span.set_attribute("gen_ai.agent.name", agent_name)
                agent_span.set_attribute("gen_ai.request.model", model)
                agent_span.set_attribute("gen_ai.agent.tools_count", len(all_tool_definitions))
                return self._do_get_or_create_agent(agent_name, model, all_tool_definitions, agent_span)
        else:
            return self._do_get_or_create_agent(agent_name, model, all_tool_definitions, None)
    
    def _do_get_or_create_agent(self, agent_name: str, model: str, all_tool_definitions: list, agent_span) -> Any:
        """Internal implementation of agent creation."""
        try:
            
            # Try to find an existing agent with this name
            existing_agent = self._find_existing_agent(agent_name)
            
            if existing_agent:
                # Update the existing agent with new model/tools if needed
                agent_kwargs: dict[str, Any] = {
                    "agent_id": existing_agent.id,
                    "model": model,
                    "instructions": self._agent_instructions,
                }
                if all_tool_definitions:
                    agent_kwargs["tools"] = all_tool_definitions
                
                self._current_agent = self._agents_client.update_agent(**agent_kwargs)
                self._current_agent_model = model
                logger.info(f"Updated existing agent: {agent_name} (ID: {self._current_agent.id})")
                
                if agent_span:
                    agent_span.set_attribute("gen_ai.agent.id", self._current_agent.id)
                    agent_span.set_attribute("gen_ai.agent.action", "updated")
                
                return self._current_agent

            # Create new agent
            agent_kwargs = {
                "model": model,
                "name": agent_name,
                "instructions": self._agent_instructions,
            }

            # Add all tool definitions (function + MCP)
            if all_tool_definitions:
                agent_kwargs["tools"] = all_tool_definitions

            self._current_agent = self._agents_client.create_agent(**agent_kwargs)
            self._current_agent_model = model
            logger.info(f"Created new agent: {agent_name} (ID: {self._current_agent.id})")
            
            if agent_span:
                agent_span.set_attribute("gen_ai.agent.id", self._current_agent.id)
                agent_span.set_attribute("gen_ai.agent.action", "created")
            
            return self._current_agent

        except Exception as e:
            if agent_span:
                from opentelemetry import trace
                agent_span.set_status(trace.StatusCode.ERROR, str(e))
            raise ProviderError(
                f"Failed to create/update agent: {e}",
                provider="azure_foundry",
                cause=e,
            )

    def _convert_tools_to_agent_format(self, tools: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
        """
        Convert tools to Azure AI Agents format.
        
        Returns:
            Tuple of (tool_definitions, mcp_tools) where:
            - tool_definitions: List of function tool definitions for the agent
              (includes A2A tools as local function calls)
            - mcp_tools: List of McpTool instances for use in run creation
            
        Note: A2A tools are registered with the A2AToolExecutor and converted to
        function tools. Azure's a2a_preview feature is broken, so we handle A2A
        calls locally using the official A2A protocol SDK.
        """
        from ez_agent.providers.a2a_client import A2AToolConfig
        
        function_tools = []
        mcp_tools = []
        
        # Clear previous A2A tools
        self._get_a2a_executor().clear()
        
        for tool in tools:
            tool_type = tool.get("type", "function")
            
            if tool_type == "mcp":
                # Create McpTool instance
                McpTool = self._azure["McpTool"]
                
                server_url = tool.get("server_url", "")
                server_label = tool.get("server_label", tool.get("name", "mcp_server"))
                allowed_tools = tool.get("allowed_tools")
                require_approval = tool.get("require_approval", "never")
                headers = tool.get("headers", {})
                
                mcp_tool = McpTool(
                    server_label=server_label,
                    server_url=server_url,
                    allowed_tools=allowed_tools,
                )
                
                # Set approval mode
                mcp_tool.set_approval_mode(require_approval)
                
                # Add any custom headers
                for key, value in headers.items():
                    mcp_tool.update_headers(key, value)
                
                mcp_tools.append(mcp_tool)
                logger.info(f"Configured MCP tool: {server_label} -> {server_url}")
            elif tool_type == "agent":
                # A2A (Agent-to-Agent) tool - handled locally via A2AToolExecutor
                # Azure's a2a_preview is broken, so we use the official A2A SDK
                name = tool.get("name", "a2a_tool")
                description = tool.get("description", f"Send a message to the {name} agent")
                agent_endpoint = tool.get("agent_endpoint")
                headers = tool.get("headers", {})
                
                if not agent_endpoint:
                    # Project connection ID not supported for local execution
                    project_connection_id = tool.get("project_connection_id")
                    if project_connection_id:
                        logger.warning(
                            f"A2A tool '{name}' uses project_connection_id which requires Azure's "
                            "a2a_preview feature. This is currently broken. Use agent_endpoint instead."
                        )
                    else:
                        logger.warning(f"A2A tool '{name}' missing agent_endpoint, skipping")
                    continue
                
                # Register with A2A executor
                a2a_config = A2AToolConfig(
                    name=name,
                    base_url=agent_endpoint,
                    description=description,
                    headers=headers,
                )
                self._get_a2a_executor().register_tool(a2a_config)
                logger.info(f"Registered A2A tool (local execution): {name} -> {agent_endpoint}")
            else:
                # Function tool
                function_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
        
        # Add A2A tools as function tools (for LLM to call)
        a2a_function_defs = self._get_a2a_executor().get_function_definitions()
        function_tools.extend(a2a_function_defs)
        
        return function_tools, mcp_tools

    def _extract_messages_from_thread(self, thread_id: str, run_id: str) -> tuple[str, list[ToolCall] | None]:
        """Extract the assistant's response from thread messages."""
        ListSortOrder = self._azure["ListSortOrder"]
        
        messages = self._agents_client.messages.list(
            thread_id=thread_id,
            order=ListSortOrder.DESCENDING,
        )
        
        content = ""
        tool_calls = []
        
        for message in messages:
            if message.run_id == run_id and message.role == "assistant":
                # Get text content
                if message.text_messages:
                    content = message.text_messages[-1].text.value
                break
        
        return content, tool_calls if tool_calls else None

    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """
        Send a completion request to Azure AI Foundry using the Agents SDK.

        Args:
            messages: List of messages in the conversation.
            model: Model deployment name to use.
            tools: Optional list of tools available to the model.
            temperature: Sampling temperature (note: may be limited by agent config).
            max_tokens: Maximum tokens to generate.

        Returns:
            Provider response with content and optional tool calls.
        """
        tracer = self._get_tracer()
        
        # Create parent span for the entire conversation turn
        if tracer:
            from opentelemetry import trace, context
            with tracer.start_as_current_span(
                f"agent_turn {self._agent_name or 'ez-agent'}",
                kind=trace.SpanKind.CLIENT,
            ) as span:
                span.set_attribute("gen_ai.system", "az.ai.agents")
                span.set_attribute("gen_ai.operation.name", "agent_turn")
                span.set_attribute("gen_ai.request.model", model)
                if self._agent_name:
                    span.set_attribute("gen_ai.agent.name", self._agent_name)
                
                # Capture current context to pass to async operations
                ctx = context.get_current()
                return await self._do_complete(messages, model, tools, temperature, max_tokens, span, ctx)
        else:
            return await self._do_complete(messages, model, tools, temperature, max_tokens, None, None)

    async def _do_complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int | None,
        parent_span,
        trace_context=None,
    ) -> ProviderResponse:
        """Internal implementation of complete with optional parent span."""
        # Attach the trace context to ensure SDK spans are nested under our parent
        token = None
        if trace_context:
            from opentelemetry import context
            token = context.attach(trace_context)
        
        tracer = self._get_tracer()
        
        try:
            agent = self._get_or_create_agent(model, tools)
            
            if parent_span:
                parent_span.set_attribute("gen_ai.agent.id", agent.id)
            
            # Create a thread span and use it as current for all thread operations
            if tracer:
                from opentelemetry import trace
                with tracer.start_as_current_span(
                    "thread",
                    kind=trace.SpanKind.CLIENT,
                ) as thread_span:
                    thread_span.set_attribute("gen_ai.agent.id", agent.id)
                    return await self._execute_thread_operations(
                        agent, messages, thread_span, parent_span
                    )
            else:
                return await self._execute_thread_operations(
                    agent, messages, None, parent_span
                )
        except ProviderError:
            raise
        except Exception as e:
            logger.exception(f"Azure Foundry completion error: {e}")
            raise ProviderError(
                f"Completion failed: {e}",
                provider="azure_foundry",
                cause=e,
            )
        finally:
            # Detach the trace context if we attached one
            if token:
                from opentelemetry import context
                context.detach(token)

    async def _execute_thread_operations(
        self,
        agent,
        messages: list[ProviderMessage],
        thread_span,
        parent_span,
    ) -> ProviderResponse:
        """Execute all thread operations within the thread span context."""
        thread = self._agents_client.threads.create()
        
        if parent_span:
            parent_span.set_attribute("gen_ai.thread.id", thread.id)
        if thread_span:
            thread_span.set_attribute("gen_ai.thread.id", thread.id)
        
        try:
            # Add messages to the thread
            for msg in messages:
                if msg.role == MessageRole.SYSTEM:
                    # System messages become part of agent instructions
                    # We handle them by updating the thread context
                    continue
                elif msg.role == MessageRole.TOOL:
                    # Tool results - skip for now, handled in tool flow
                    continue
                else:
                    role = "user" if msg.role == MessageRole.USER else "assistant"
                    self._agents_client.messages.create(
                        thread_id=thread.id,
                        role=role,
                        content=msg.content,
                    )

            # Build run kwargs with MCP tool resources
            run_kwargs: dict[str, Any] = {
                "thread_id": thread.id,
                "agent_id": agent.id,
            }
            
            # Collect MCP tool headers and merge all tool resources
            mcp_headers: dict[str, str] = {}
            merged_resources: dict[str, Any] = {}
            
            if self._current_mcp_tools:
                # Merge all MCP tool resources
                merged_resources["mcp"] = []
                for mcp_tool in self._current_mcp_tools:
                    for mcp_resource in mcp_tool.resources.get("mcp", []):
                        merged_resources["mcp"].append(mcp_resource)
                    # Collect headers from all MCP tools
                    mcp_headers.update(mcp_tool.headers)
                logger.info(f"Running with MCP tool resources: {merged_resources}")
            
            # Note: A2A tools don't have separate resources - they are passed as tool definitions
            
            if merged_resources:
                run_kwargs["tool_resources"] = merged_resources
            
            # Create run and poll for completion (to handle MCP approvals)
            run = self._agents_client.runs.create(**run_kwargs)
            logger.debug(f"Created run: {run.id}, status: {run.status}")
            
            import asyncio
            SubmitToolApprovalAction = self._azure["SubmitToolApprovalAction"]
            RequiredMcpToolCall = self._azure["RequiredMcpToolCall"]
            ToolApproval = self._azure["ToolApproval"]
            ToolOutput = self._azure["ToolOutput"]
            
            tool_calls = None
            poll_interval = 0.5  # Start with 0.5s
            max_poll_interval = 2.0  # Cap at 2s
            
            while run.status in ["queued", "in_progress", "requires_action"]:
                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, max_poll_interval)  # Exponential backoff
                run = self._agents_client.runs.get(thread_id=thread.id, run_id=run.id)
                logger.debug(f"Run status: {run.status}")
                
                if run.status == "requires_action" and run.required_action:
                    # Check if this is an MCP tool approval request
                    if isinstance(run.required_action, SubmitToolApprovalAction):
                        approval_tool_calls = run.required_action.submit_tool_approval.tool_calls
                        if not approval_tool_calls:
                            logger.warning("No tool calls to approve - cancelling run")
                            self._agents_client.runs.cancel(thread_id=thread.id, run_id=run.id)
                            break
                        
                        tool_approvals = []
                        for tool_call in approval_tool_calls:
                            if isinstance(tool_call, RequiredMcpToolCall):
                                logger.info(f"Auto-approving MCP tool call: {tool_call.id}")
                                # Inject trace context for distributed tracing
                                trace_headers = self._inject_trace_context(mcp_headers.copy())
                                tool_approvals.append(
                                    ToolApproval(
                                        tool_call_id=tool_call.id,
                                        approve=True,
                                        headers=trace_headers,
                                    )
                                )
                        
                        if tool_approvals:
                            logger.info(f"Submitting {len(tool_approvals)} MCP tool approvals")
                            self._agents_client.runs.submit_tool_outputs(
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_approvals=tool_approvals,
                            )
                    else:
                        # Function tool calls - check for A2A tools to execute locally
                        tool_calls = []
                        a2a_tool_outputs = []
                        
                        if hasattr(run.required_action, 'submit_tool_outputs') and run.required_action.submit_tool_outputs:
                            a2a_executor = self._get_a2a_executor()
                            
                            for tc in run.required_action.submit_tool_outputs.tool_calls:
                                if a2a_executor.is_a2a_tool_call(tc.function.name):
                                    # A2A tool - execute locally via A2A protocol
                                    logger.info(f"Executing A2A tool call locally: {tc.function.name}")
                                    try:
                                        result = await a2a_executor.execute(tc.function.name, tc.function.arguments)
                                        a2a_tool_outputs.append(ToolOutput(
                                            tool_call_id=tc.id,
                                            output=result,
                                        ))
                                        logger.info(f"A2A tool {tc.function.name} executed successfully")
                                    except Exception as e:
                                        logger.error(f"A2A tool {tc.function.name} failed: {e}")
                                        a2a_tool_outputs.append(ToolOutput(
                                            tool_call_id=tc.id,
                                            output=f"Error executing A2A tool: {str(e)}",
                                        ))
                                else:
                                    # Regular function tool - return to caller
                                    tool_calls.append(ToolCall(
                                        id=tc.id,
                                        name=tc.function.name,
                                        arguments=tc.function.arguments,
                                    ))
                        
                        # Submit A2A tool outputs if any
                        if a2a_tool_outputs:
                            logger.info(f"Submitting {len(a2a_tool_outputs)} A2A tool outputs")
                            self._agents_client.runs.submit_tool_outputs(
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_outputs=a2a_tool_outputs,
                            )
                            # If only A2A calls, continue polling; else break to return regular calls
                            if not tool_calls:
                                continue
                        
                        if tool_calls:
                            break  # Exit loop to return tool calls to caller

            if run.status == "failed":
                raise ProviderError(
                    f"Run failed: {run.last_error}",
                    provider="azure_foundry",
                )

            # Extract response from messages
            content, _ = self._extract_messages_from_thread(thread.id, run.id)

            return ProviderResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason="tool_calls" if tool_calls else "stop",
                usage=None,  # Usage info not directly available from agents API
            )

        finally:
            # Clean up thread
            try:
                self._agents_client.threads.delete(thread.id)
            except Exception:
                pass

    async def stream(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a completion response from Azure AI Foundry using the Agents SDK.

        Args:
            messages: List of messages in the conversation.
            model: Model deployment name to use.
            tools: Optional list of tools available to the model.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Yields:
            Stream chunks with content deltas.
        """
        # For async generators, we use trace.use_span() to activate spans for SDK calls
        tracer = self._get_tracer()
        parent_span = None
        thread_span = None
        
        if tracer:
            from opentelemetry import trace
            # Create parent span for the entire stream operation
            parent_span = tracer.start_span(
                f"agent_stream {self._agent_name or 'ez-agent'}",
                kind=trace.SpanKind.CLIENT,
            )
            parent_span.set_attribute("gen_ai.system", "az.ai.agents")
            parent_span.set_attribute("gen_ai.operation.name", "agent_stream")
            parent_span.set_attribute("gen_ai.request.model", model)
            if self._agent_name:
                parent_span.set_attribute("gen_ai.agent.name", self._agent_name)
        
        try:
            # Use parent span as current for agent operations
            if parent_span:
                from opentelemetry import trace
                with trace.use_span(parent_span, end_on_exit=False):
                    agent = self._get_or_create_agent(model, tools)
            else:
                agent = self._get_or_create_agent(model, tools)
            
            if parent_span:
                parent_span.set_attribute("gen_ai.agent.id", agent.id)
        
            # Create a thread span to track the entire conversation
            if tracer:
                from opentelemetry import trace
                thread_span = tracer.start_span(
                    "thread",
                    kind=trace.SpanKind.CLIENT,
                )
                thread_span.set_attribute("gen_ai.agent.id", agent.id)
            
            # Use thread span as current for all thread operations
            def create_thread_and_messages():
                thread = self._agents_client.threads.create()
                
                if parent_span:
                    parent_span.set_attribute("gen_ai.thread.id", thread.id)
                if thread_span:
                    thread_span.set_attribute("gen_ai.thread.id", thread.id)
                
                # Add messages to the thread
                for msg in messages:
                    if msg.role == MessageRole.SYSTEM:
                        continue
                    elif msg.role == MessageRole.TOOL:
                        continue
                    else:
                        role = "user" if msg.role == MessageRole.USER else "assistant"
                        self._agents_client.messages.create(
                            thread_id=thread.id,
                            role=role,
                            content=msg.content,
                        )
                return thread
            
            if thread_span:
                from opentelemetry import trace
                with trace.use_span(thread_span, end_on_exit=False):
                    thread = create_thread_and_messages()
            else:
                thread = create_thread_and_messages()

            # Get required types
            SubmitToolApprovalAction = self._azure["SubmitToolApprovalAction"]
            RequiredMcpToolCall = self._azure["RequiredMcpToolCall"]
            ToolApproval = self._azure["ToolApproval"]
            ToolOutput = self._azure["ToolOutput"]

            # Build run kwargs with MCP and A2A tool resources if configured
            run_kwargs: dict[str, Any] = {
                "thread_id": thread.id,
                "agent_id": agent.id,
            }
            
            # Collect MCP tool headers and merge all tool resources
            mcp_headers: dict[str, str] = {}
            merged_resources: dict[str, Any] = {}
            
            if self._current_mcp_tools:
                merged_resources["mcp"] = []
                for mcp_tool in self._current_mcp_tools:
                    for mcp_resource in mcp_tool.resources.get("mcp", []):
                        merged_resources["mcp"].append(mcp_resource)
                    # Collect headers from all MCP tools
                    mcp_headers.update(mcp_tool.headers)
                logger.info(f"Streaming with MCP tool resources: {merged_resources}")
            
            # Note: A2A tools don't have separate resources - they are passed as tool definitions
            
            if merged_resources:
                run_kwargs["tool_resources"] = merged_resources

            # Helper to run SDK calls within thread span context
            def sdk_call(func, *args, **kwargs):
                if thread_span:
                    from opentelemetry import trace
                    with trace.use_span(thread_span, end_on_exit=False):
                        return func(*args, **kwargs)
                return func(*args, **kwargs)

            # Use polling-based approach to properly handle MCP tool approvals
            run = sdk_call(self._agents_client.runs.create, **run_kwargs)
            logger.debug(f"Created run: {run.id}, status: {run.status}")
            
            import asyncio
            poll_interval = 0.5  # Start with 0.5s
            max_poll_interval = 2.0  # Cap at 2s
            
            while run.status in ["queued", "in_progress", "requires_action"]:
                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.5, max_poll_interval)  # Exponential backoff
                run = sdk_call(self._agents_client.runs.get, thread_id=thread.id, run_id=run.id)
                logger.debug(f"Run status: {run.status}")
                
                if run.status == "requires_action":
                    # Check if this is a tool approval request (MCP or A2A)
                    if isinstance(run.required_action, SubmitToolApprovalAction):
                        tool_calls = run.required_action.submit_tool_approval.tool_calls
                        if not tool_calls:
                            logger.warning("No tool calls to approve - cancelling run")
                            sdk_call(self._agents_client.runs.cancel, thread_id=thread.id, run_id=run.id)
                            break
                        
                        tool_approvals = []
                        for tool_call in tool_calls:
                            if isinstance(tool_call, RequiredMcpToolCall):
                                logger.info(f"Auto-approving MCP tool call: {tool_call.id}")
                                # Inject trace context for distributed tracing
                                trace_headers = self._inject_trace_context(mcp_headers.copy())
                                tool_approvals.append(
                                    ToolApproval(
                                        tool_call_id=tool_call.id,
                                        approve=True,
                                        headers=trace_headers,
                                    )
                                )
                        
                        if tool_approvals:
                            logger.info(f"Submitting {len(tool_approvals)} MCP tool approvals")
                            sdk_call(
                                self._agents_client.runs.submit_tool_outputs,
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_approvals=tool_approvals,
                            )
                    else:
                        # Function tool calls - check for A2A tools to execute locally
                        final_tool_calls = []
                        a2a_tool_outputs = []
                        
                        if hasattr(run.required_action, 'submit_tool_outputs'):
                            a2a_executor = self._get_a2a_executor()
                            
                            for tc in run.required_action.submit_tool_outputs.tool_calls:
                                if a2a_executor.is_a2a_tool_call(tc.function.name):
                                    # A2A tool - execute locally via A2A protocol
                                    logger.info(f"Executing A2A tool call locally (stream): {tc.function.name}")
                                    try:
                                        result = await a2a_executor.execute(tc.function.name, tc.function.arguments)
                                        a2a_tool_outputs.append(ToolOutput(
                                            tool_call_id=tc.id,
                                            output=result,
                                        ))
                                        logger.info(f"A2A tool {tc.function.name} executed successfully")
                                    except Exception as e:
                                        logger.error(f"A2A tool {tc.function.name} failed: {e}")
                                        a2a_tool_outputs.append(ToolOutput(
                                            tool_call_id=tc.id,
                                            output=f"Error executing A2A tool: {str(e)}",
                                        ))
                                else:
                                    # Regular function tool - yield back to caller
                                    final_tool_calls.append(ToolCall(
                                        id=tc.id,
                                        name=tc.function.name,
                                        arguments=tc.function.arguments,
                                    ))
                        
                        # Submit A2A tool outputs if any
                        if a2a_tool_outputs:
                            logger.info(f"Submitting {len(a2a_tool_outputs)} A2A tool outputs (stream)")
                            sdk_call(
                                self._agents_client.runs.submit_tool_outputs,
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_outputs=a2a_tool_outputs,
                            )
                            # If only A2A calls, continue polling; else return regular calls
                            if not final_tool_calls:
                                continue
                        
                        if final_tool_calls:
                            yield StreamChunk(
                                content="",
                                is_final=True,
                                tool_calls=final_tool_calls,
                                finish_reason="tool_calls",
                            )
                            return
            
            # Run completed - get the response
            if run.status == "completed":
                # Fetch messages from the thread
                thread_messages = sdk_call(
                    self._agents_client.messages.list,
                    thread_id=thread.id,
                    order=self._azure["ListSortOrder"].DESCENDING,
                )
                
                # Get the latest assistant message
                for msg in thread_messages:
                    if msg.role == "assistant":
                        for content_item in msg.content:
                            if hasattr(content_item, 'text') and content_item.text:
                                response_text = content_item.text.value
                                yield StreamChunk(
                                    content=response_text,
                                    is_final=False,
                                )
                        break
                
                yield StreamChunk(
                    content="",
                    is_final=True,
                    finish_reason="stop",
                )
            elif run.status == "failed":
                error_msg = str(run.last_error) if run.last_error else "Unknown error"
                logger.error(f"Run failed: {error_msg}")
                yield StreamChunk(
                    content=f"Error: {error_msg}",
                    is_final=True,
                    finish_reason="failed",
                )
            elif run.status == "cancelled":
                yield StreamChunk(
                    content="",
                    is_final=True,
                    finish_reason="cancelled",
                )
                
        except GeneratorExit:
            # Normal generator cleanup - don't log as error
            pass
        except ProviderError:
            if parent_span:
                from opentelemetry import trace
                parent_span.set_status(trace.StatusCode.ERROR)
            raise
        except Exception as e:
            logger.exception(f"Azure Foundry stream error: {e}")
            if parent_span:
                from opentelemetry import trace
                parent_span.set_status(trace.StatusCode.ERROR, str(e))
            raise ProviderError(
                f"Stream failed: {e}",
                provider="azure_foundry",
                cause=e,
            )
        finally:
            # Clean up thread (within span context if available)
            try:
                if thread_span:
                    from opentelemetry import trace
                    with trace.use_span(thread_span, end_on_exit=False):
                        self._agents_client.threads.delete(thread.id)
                else:
                    self._agents_client.threads.delete(thread.id)
            except Exception:
                # Ignore errors during thread cleanup - thread may already be deleted
                pass
            
            # End spans
            if thread_span:
                thread_span.end()
            if parent_span:
                parent_span.end()

    async def health_check(self) -> bool:
        """Check if the provider is healthy."""
        try:
            # Verify we can access the agents client
            _ = self._agents_client
            return True
        except Exception as e:
            logger.warning(f"Azure Foundry health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the provider and clean up resources."""
        # Clean up the agent only if persist_agent is False
        if self._current_agent and not self._persist_agent:
            tracer = self._get_tracer()
            delete_span = None
            if tracer:
                from opentelemetry import trace
                delete_span = tracer.start_span(
                    "agent_delete",
                    kind=trace.SpanKind.CLIENT,
                )
                delete_span.set_attribute("gen_ai.agent.id", self._current_agent.id)
                delete_span.set_attribute("gen_ai.agent.name", self._agent_name or "unknown")
            
            try:
                self._agents_client.delete_agent(self._current_agent.id)
                logger.info(f"Deleted agent: {self._agent_name} (ID: {self._current_agent.id})")
            except Exception as e:
                logger.warning(f"Failed to delete agent: {e}")
                if delete_span:
                    from opentelemetry import trace
                    delete_span.set_status(trace.StatusCode.ERROR, str(e))
            finally:
                if delete_span:
                    delete_span.end()
        elif self._current_agent and self._persist_agent:
            logger.info(f"Persisting agent: {self._agent_name} (ID: {self._current_agent.id})")
        
        self._current_agent = None
        self._current_agent_model = None
        
        # Close agents client if it has a close method
        if hasattr(self._agents_client, 'close'):
            try:
                self._agents_client.close()
            except Exception:
                # Ignore errors during client cleanup - client may already be closed
                pass
