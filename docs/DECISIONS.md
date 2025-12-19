# EZ-Agent Architecture Decisions

This document records key architectural decisions made during EZ-Agent development.
Each decision includes context, options considered, and rationale.

---

## ADR-001: Storage Abstraction with Protocol-Based Interfaces

**Date**: 2024-12-12  
**Status**: Accepted

### Context
The framework needs to store tasks and conversations. Initial implementation uses in-memory storage, but production deployments may need SQLite, Redis, or other backends.

### Decision
Use Python Protocol classes (`ITaskStore`, `IConversationStore`) with dependency injection. Start with in-memory implementation.

### Consequences
- ✅ Easy to add new storage backends without changing core code
- ✅ Testable with mock implementations
- ❌ Slightly more complex than direct implementation

---

## ADR-002: Single Agent Per Process

**Date**: 2024-12-12  
**Status**: Accepted

### Context
Should the CLI support running multiple agents from different config files in one process?

### Decision
No. Each agent runs in its own process. Multiple agents require multiple `ezagent run` commands.

### Consequences
- ✅ Simpler architecture and resource isolation
- ✅ Clear failure boundaries
- ❌ More processes for multi-agent scenarios (use docker-compose)

---

## ADR-003: Feature Flags as Boolean Dictionary

**Date**: 2024-12-12  
**Status**: Accepted

### Context
How should feature flags be represented in configuration?

### Decision
Simple `{"feature_name": true/false}` dictionary in the `features` section.

### Alternatives Considered
- Complex conditional logic (rejected: overkill for v1)
- Environment-based feature gates (rejected: less explicit)

### Consequences
- ✅ Simple to understand and use
- ✅ Easy to extend later
- ❌ No conditional or environment-based logic (yet)

---

## ADR-004: Tool Execution as Local Python Functions

**Date**: 2024-12-12  
**Status**: Accepted

### Context
How should tools be executed? Options include Docker sandboxing, subprocess isolation, or direct function calls.

### Decision
Tools are plain Python functions executed directly in the agent process, following the Azure AI Agents `FunctionTool` pattern.

### Pattern
- Functions use docstrings for descriptions (auto-parsed)
- Type hints generate JSON schemas
- Results returned as JSON strings
- Tool calls correlated by `tool_call_id`

### Consequences
- ✅ Simple, fast execution
- ✅ Full access to Python ecosystem
- ❌ No sandboxing (trusted tools only)

---

## ADR-005: A2A Protocol for HTTP Mode

**Date**: 2024-12-12  
**Status**: Accepted

### Context
What protocol should the HTTP mode expose?

### Decision
Implement the A2A (Agent-to-Agent) protocol specification from https://a2a-protocol.org/latest/specification/

### Key Endpoints
- `POST /v1/message:send` - Synchronous message
- `POST /v1/message:stream` - SSE streaming
- `GET /v1/tasks/{id}` - Task status
- `GET /.well-known/agent-card.json` - Agent discovery

### Consequences
- ✅ Interoperability with other A2A-compliant agents
- ✅ Well-defined protocol with clear semantics
- ❌ More complex than a simple REST API

---

## ADR-006: Progress Tracking in Markdown Files

**Date**: 2024-12-12  
**Status**: Accepted

### Context
How should implementation progress and decisions be tracked for AI agent context?

### Decision
Use `docs/PROGRESS.md` for status tracking and `docs/DECISIONS.md` for architectural decisions.

### Consequences
- ✅ Human and AI readable
- ✅ Version controlled
- ✅ Easy to update

---

## ADR-007: Azure AI Foundry as First Provider

**Date**: 2024-12-12  
**Status**: Accepted  
**Updated**: 2024-12-13

### Context
Which LLM provider should be implemented first?

### Decision
Azure AI Foundry using the `azure-ai-agents` SDK with `DefaultAzureCredential`.

The implementation uses the Agents/Threads/Runs pattern which works with **any model** deployed in Azure AI Foundry:
- Azure OpenAI models (GPT-4, GPT-4o, etc.)
- Microsoft models (Phi-3, Phi-4, etc.)
- Third-party models (Mistral, Llama, Cohere, etc.)

### Agent Naming and Persistence
- Agents are created in Azure Foundry with name pattern: `ez-agent-{name}` (where `name` comes from YAML config)
- On startup, existing agents with matching names are reused and updated
- By default, agents are deleted on app shutdown (`persist_agent: false`)
- Set `persist_agent: true` in Azure config to keep agents after shutdown

### Consequences
- ✅ Enterprise-ready with managed identity support
- ✅ Works with any model type in Azure AI Foundry (not just OpenAI)
- ✅ Agents can be persisted for reuse across sessions
- ❌ Requires Azure subscription for testing

---

## ADR-008: Azure Agent Naming and Persistence

**Date**: 2024-12-13  
**Status**: Accepted

### Context
When using Azure AI Foundry, agents are created in the cloud. We need to:
1. Give agents consistent, identifiable names
2. Allow agents to be reused across app restarts
3. Control whether agents persist after app shutdown

### Decision
- Agent naming convention: `ez-agent-{name}` where `{name}` comes from the YAML config
- On startup, search for existing agents with matching name and reuse/update them
- Add `persist_agent` setting (default: `false`) to control cleanup behavior

### Configuration
```yaml
configuration:
  azure:
    endpoint: https://...
    auth_method: default_credential
    persist_agent: false  # true = keep agent after shutdown
```

### Consequences
- ✅ Agents are easily identifiable in Azure portal (ez-agent-mybot, ez-agent-assistant)
- ✅ Faster startup when reusing existing agents
- ✅ Reduced Azure resource usage with automatic cleanup
- ✅ Optional persistence for production scenarios
- ❌ Agent state (instructions, tools) is updated on each restart

---

## ADR-009: Azure AI Foundry Tracing

**Date**: 2024-12-13  
**Status**: Accepted  
**Updated**: 2024-12-13

### Context
Observability is critical for production AI agents. Azure AI Foundry provides OpenTelemetry-based tracing that captures:
- Agent creation, updates, and deletion
- Thread and run lifecycle events
- Tool invocations and results
- LLM calls with latency and token usage

We need to support this tracing with minimal configuration while keeping it optional.

### Decision
- Add optional `tracing` configuration under `azure` config
- Support two modes: Application Insights (production) and Console (development)
- Use `AIAgentsInstrumentor` from `azure-ai-agents` for automatic instrumentation
- Wrap all agent operations in a parent `agent_turn` span for cleaner trace hierarchy
- Optional `console_tracing` for local debugging (disabled by default - very verbose)
- Optional `capture_message_content` for debugging (disabled by default for privacy)
- Optional `service_name` for multi-app scenarios

### Configuration
```yaml
configuration:
  azure:
    endpoint: https://...
    auth_method: default_credential
    tracing:
      enabled: true
      application_insights_connection_string: "InstrumentationKey=..." # Optional
      console_tracing: false  # Set to true for verbose JSON span output
      capture_message_content: false  # Warning: may capture sensitive data
      service_name: my-agent  # For filtering in Application Insights
```

### Trace Hierarchy
With the parent span wrapper, traces are organized as:
```
agent_turn ez-agent-{name} (parent span)
├── create_thread
├── create_message
├── process_thread_run
│   └── POST /runs
└── ThreadsOperations.delete
```

### Dependencies
Tracing requires optional dependencies:
```bash
pip install ez-agent[tracing]
```

This installs:
- `azure-monitor-opentelemetry` - Azure Monitor exporter
- `azure-core-tracing-opentelemetry` - Azure Core tracing support  
- `opentelemetry-sdk` - OpenTelemetry core SDK

### Consequences
- ✅ Full visibility into agent operations in Azure Monitor
- ✅ Integration with Azure AI Foundry portal tracing view
- ✅ Clean trace hierarchy with parent `agent_turn` spans
- ✅ Console mode for local development/debugging
- ✅ Privacy-conscious defaults (message content not captured)
- ✅ Optional dependency - no overhead when not used
- ❌ Requires Application Insights for production tracing

---

## ADR-010: Terminal Mode Clean Output

**Date**: 2024-12-13  
**Status**: Accepted

### Context
When running agents in terminal mode, log output from Azure SDK, urllib3, and OpenTelemetry was interfering with the conversation display, making it hard to read agent responses.

### Decision
- Start terminal mode with logs disabled (WARNING level)
- Add `/logs` command to toggle log visibility (cycles: OFF → INFO → DEBUG → OFF)
- Add `/status` command to check agent health
- Suppress noisy third-party loggers (azure, urllib3, httpx, asyncio, opentelemetry)

### Terminal Commands
```
/new    - Start a new conversation
/clear  - Clear the screen
/logs   - Toggle log output (OFF → INFO → DEBUG → OFF)
/status - Show agent health status
/exit   - Exit the agent
/help   - Show help
```

### Consequences
- ✅ Clean conversation display by default
- ✅ Easy debugging with `/logs` toggle
- ✅ No log noise during normal use
- ❌ Logs not visible by default (use `/logs` to enable)

---

## ADR-011: MCP (Model Context Protocol) Tool Support

**Date**: 2024-12-16  
**Status**: Accepted

### Context
Users want to connect agents to external tools via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/). MCP is an open protocol for managing how LLMs interact with external tools. Azure AI Foundry supports MCP tools through the `McpTool` class in the preview SDK.

### Decision
- Add MCP as a tool type (`type: mcp`) in the tool configuration
- Use Azure AI Agents SDK preview (>=1.2.0b6) which includes `McpTool` support
- Configuration options:
  - `server_url`: HTTP endpoint of the MCP server (required)
  - `server_label`: Unique identifier for the server (auto-generated from name if not provided)
  - `allowed_tools`: Optional list to restrict which tools from the server
  - `require_approval`: `"never"` (default) or `"always"` for interactive approval
  - `headers`: Optional custom headers for authentication

### Configuration
```yaml
tools:
  - name: github_mcp
    type: mcp
    description: GitHub MCP Server for Azure REST API specs
    server_url: https://gitmcp.io/Azure/azure-rest-api-specs
    server_label: github
    allowed_tools:
      - search_azure_rest_api_code
    require_approval: never  # Auto-approve tool calls
    headers:
      Authorization: "Bearer ${MCP_API_KEY}"
```

### Implementation
1. `ToolConfig` model extended with MCP-specific fields
2. `MCPApprovalMode` enum for approval modes
3. `_convert_tools_to_agent_format()` returns separate function tools and MCP tools
4. MCP tool definitions added to agent, resources passed at run creation
5. Auto-approval logic for when `require_approval: always` is set

### Alternatives Considered
- **Build custom MCP client**: Would require significant work to implement MCP protocol handling
- **Wait for stable SDK**: Would delay feature, but preview SDK is functional

### Consequences
- ✅ Agents can connect to any HTTP MCP server
- ✅ Full control over allowed tools and approval flow
- ✅ Consistent with Azure AI Foundry's MCP support
- ❌ Requires preview SDK (1.2.0b6+) until MCP support is GA
- ❌ HTTP MCP only (no stdio/SSE transport support yet)

---

## ADR-012: A2A (Agent-to-Agent) Tool Support with Local Execution

**Date**: 2024-12-16  
**Status**: Accepted

### Context
Users want to orchestrate multiple agents, where one agent can call another agent as a tool. Azure AI Foundry provides an `a2a_preview` feature through the `ConnectedAgentTool` class, but this feature is currently broken at the service level (causes immediate `server_error` on any run).

The [A2A (Agent-to-Agent) Protocol](https://a2a-protocol.org/latest/specification/) is an open standard by Google/Linux Foundation for agent-to-agent communication. An official Python SDK (`a2a-sdk`) is available.

### Decision
Instead of using Azure's broken `a2a_preview` feature, implement A2A tool execution locally using the official A2A Python SDK:

1. Add `a2a-sdk` as a dependency
2. Create `A2AClient` class supporting both REST (`/v1/message:send`) and JSON-RPC bindings
3. Create `A2AToolExecutor` to manage A2A tools and execute them locally
4. Register A2A tools as function tools with `a2a_` prefix (e.g., `a2a_research_agent`)
5. Intercept A2A function calls in the run loop, execute locally, submit results to Azure

### Configuration
```yaml
tools:
  - name: research_agent
    type: agent
    description: A specialized discovery agent
    agent_endpoint: https://research-agent.example.com
    headers:  # Optional: custom headers
      Authorization: "Bearer ${AGENT_API_KEY}"
```

### Implementation Details
- `A2AToolConfig`: Dataclass for tool configuration (name, base_url, description, headers)
- `A2AClient`: HTTP client with `send_message()` supporting REST and JSON-RPC fallback
- `A2AToolExecutor`: Manages A2A tools, provides function definitions, executes calls
- `A2AMessage`/`A2AResponse`: Data classes for A2A protocol messages

### A2A Protocol Support
- **REST binding**: `POST /v1/message:send` with JSON body
- **JSON-RPC binding**: Standard JSON-RPC 2.0 with `SendMessage` method
- **Message format**: `{"role": "user", "parts": [{"text": "..."}], "messageId": "uuid"}`
- **Response parsing**: Handles both `task` (with artifacts) and direct `message` responses

### Alternatives Considered
- **Wait for Azure fix**: Unknown timeline, blocks users
- **Use `project_connection_id`**: Requires agents in same/connected projects, not flexible
- **Build custom protocol**: Already have A2A standard with official SDK

### Consequences
- ✅ Works around Azure's broken `a2a_preview` feature
- ✅ Full A2A protocol compliance using official SDK
- ✅ Supports any A2A-compliant agent (not just Azure Foundry)
- ✅ Flexible - connect to agents hosted anywhere
- ✅ Clean function tool interface for the LLM
- ❌ Adds `a2a-sdk` dependency
- ❌ A2A calls executed locally (not by Azure service)

---

## ADR-013: Helm Charts for Kubernetes Deployment

**Date**: 2024-12-18  
**Status**: Accepted

### Context
Users need to deploy EZ-Agent to production Kubernetes environments with:
- Application Gateway for Containers (AGC) for ingress
- mTLS between gateway and pods
- Workload Identity for Azure AI Foundry access
- Secrets Store CSI Driver for TLS certificates from Key Vault
- Multiple agents sharing infrastructure

### Decision
Create two Helm charts following the same pattern as the MCP server charts:

1. **`charts/ez-agent`**: Generic agent deployment chart
   - Deployment with configurable resources, replicas, HPA
   - Service for cluster-internal communication
   - ConfigMap for agent YAML configuration
   - BackendTLSPolicy for AGC mTLS
   - NetworkPolicy for security
   - PodDisruptionBudget for availability
   - HealthCheckPolicy for AGC health probes

2. **`charts/agents-infrastructure`**: Shared infrastructure chart
   - Gateway resource for AGC
   - HTTPRoute for path-based routing (`/agents/<name>`)
   - ServiceAccount with Workload Identity
   - SecretProviderClass for Key Vault TLS sync

3. **Extend configuration model** with deployment settings:
   - `DeploymentConfig`: namespace, replicas, service account
   - `ImageConfig`: registry, repository, tag, pull policy
   - `RoutingConfig`: path, port, protocol
   - `ResourceConfig`: requests/limits for CPU/memory
   - `TLSConfig`: cert paths, secret names
   - `AutoscalingConfig`: HPA settings
   - `AGCConfig`: hostname, subnet CIDR

4. **CLI TLS support**: Add `--tls-cert` and `--tls-key` options to `ezagent run`

5. **Deploy command**: Generate Helm values.yaml from agent configuration

### Configuration Example
```yaml
configuration:
  deployment:
    enabled: true
    namespace: agents
    image:
      registry: myacr.azurecr.io
      tag: v1.0.0
    routing:
      path: my-agent
      port: 8443
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
    replicas: 2
    autoscaling:
      enabled: true
    tls:
      enabled: true
    agc:
      hostname: aidev.appliances-ppe.azure.com
```

### Deployment Workflow
```bash
# 1. Generate Helm values from agent config
ezagent deploy -c agent.yaml -t kubernetes -o ./deploy

# 2. Deploy agent
helm install my-agent ./charts/ez-agent -n agents -f ./deploy/values.yaml

# 3. Update infrastructure routes
helm upgrade agents-infrastructure ./charts/agents-infrastructure \
  --set "agents[0].name=my-agent"
```

### Alternatives Considered
- **Kustomize**: Less flexibility for parameterization
- **Raw manifests**: No templating, harder to maintain
- **Operator pattern**: Overkill for current requirements

### Consequences
- ✅ Consistent deployment across agents
- ✅ Reusable infrastructure (one gateway for all agents)
- ✅ Production-ready with mTLS, HPA, PDB
- ✅ Easy to add new agents by extending values
- ✅ `ezagent deploy` generates values from config
- ❌ Two-step deployment (infrastructure + agents)
- ❌ Requires Helm knowledge for customization

---

## Template for New Decisions

```markdown
## ADR-XXX: [Title]

**Date**: YYYY-MM-DD  
**Status**: Proposed | Accepted | Deprecated | Superseded

### Context
[What is the issue?]

### Decision
[What was decided?]

### Alternatives Considered
[What other options were evaluated?]

### Consequences
- ✅ [Positive outcome]
- ❌ [Negative outcome or trade-off]
```
