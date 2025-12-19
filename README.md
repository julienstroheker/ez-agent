# EZ-Agent

A CLI framework for developing, testing, and deploying AI agents using YAML configuration.

## Overview

EZ-Agent enables developers to focus on agent behavior through configuration rather than infrastructure. Define your agent in YAML, test locally in terminal mode, and deploy to production with HTTP/A2A protocol support.

## Features

- **YAML Configuration**: Define agents declaratively without writing boilerplate code
- **Multiple Run Modes**: Terminal (local testing) and HTTP (production with A2A protocol)
- **Provider Abstraction**: Support for Azure AI Foundry (any model), with extensible interface for other providers
- **Tool System**: Define tools as Python functions with automatic schema generation
- **Middleware Pipeline**: Pluggable logging, authentication, and metrics
- **A2A Protocol**: Full compliance with the Agent-to-Agent protocol specification
- **Observability**: Optional OpenTelemetry tracing with Azure Application Insights integration

## Installation

```bash
pip install ez-agent
```

Or install from source:

```bash
git clone https://github.com/julienstroheker/ez-agent.git
cd ez-agent
pip install -e ".[dev]"
```

### Optional Dependencies

```bash
# For OpenTelemetry tracing (Azure Application Insights)
pip install ez-agent[tracing]
```

## Quick Start

### 1. Create an agent configuration

```yaml
# my-agent.yaml
name: MyAssistant
description: A helpful AI assistant
version: 1.0.0
instructions: |
  You are a helpful assistant that answers questions clearly and concisely.
  Always be polite and informative.
model: gpt-4o

configuration:
  provider: azure_foundry
  azure:
    endpoint: ${AZURE_AI_ENDPOINT}
    auth_method: default_credential

features:
  streaming: true
  a2a_protocol: true

tools: []
```

### 2. Run in terminal mode (local testing)

```bash
ezagent run -c my-agent.yaml -m terminal
```

### 3. Run in HTTP mode (production)

```bash
ezagent run -c my-agent.yaml -m http --port 8000
```

### 4. Validate configuration

```bash
ezagent validate -c my-agent.yaml
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `ezagent run` | Run an agent from configuration |
| `ezagent init` | Interactive scaffolding for new agent |
| `ezagent validate` | Validate agent configuration file |


## Configuration Reference

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent name |
| `description` | string | Yes | Agent description |
| `version` | string | Yes | Semantic version |
| `instructions` | string | Yes | System instructions for the agent |
| `model` | string | Yes | Model identifier |
| `configuration` | object | No | Provider and runtime settings |
| `features` | object | No | Feature flags (boolean dict) |
| `tools` | array | No | Tool definitions |

### Configuration object

```yaml
configuration:
  provider: azure_foundry  # Provider to use
  azure:
    endpoint: ${AZURE_AI_ENDPOINT}
    auth_method: default_credential  # or api_key, managed_identity
    api_key: ${AZURE_AI_API_KEY}  # if auth_method is api_key
    persist_agent: false  # Keep agent in Azure after shutdown (default: false)
    tracing:  # Optional: OpenTelemetry tracing
      enabled: true
      application_insights_connection_string: ${APP_INSIGHTS_CONNECTION_STRING}
      capture_message_content: false  # Privacy: don't log message content
      service_name: my-agent  # For filtering in Application Insights
  logging:
    level: INFO
    format: json
  auth:
    enabled: false
    type: bearer  # or api_key, oauth2
```

### Tools

```yaml
tools:
  # Function tool - Python function
  - name: get_weather
    type: function
    module: my_tools.weather
    function: get_current_weather
  
  # HTTP tool - REST API endpoint
  - name: search_web
    type: http
    endpoint: https://api.search.com/v1/search
    method: POST
  
  # MCP tool - Model Context Protocol server
  - name: github_mcp
    type: mcp
  
  # A2A tool - Agent-to-Agent protocol
  - name: research_agent
    type: agent
    description: GitHub MCP Server for Azure REST API specs
    server_url: https://gitmcp.io/Azure/azure-rest-api-specs
    server_label: github
    allowed_tools:  # Optional: restrict which tools from the server
      - search_azure_rest_api_code
    require_approval: never  # 'never' or 'always' (default: never)
```

### MCP (Model Context Protocol) Tools

EZ-Agent supports connecting to HTTP-based MCP servers as tools. This allows your agent to use external tools exposed via the [Model Context Protocol](https://modelcontextprotocol.io/).

```yaml
tools:
  # Connect to any HTTP MCP server
  - name: my_mcp_server
    type: mcp
    server_url: https://your-mcp-server.com/mcp
    server_label: my_server  # Unique identifier (alphanumeric + underscores only)
    allowed_tools:           # Optional: filter which tools to expose
      - tool_name_1
      - tool_name_2
    require_approval: never  # Set to 'always' for interactive approval
    headers:                 # Optional: custom headers for authentication
      Authorization: "Bearer ${MCP_API_KEY}"
```

**Note**: MCP tool support requires `azure-ai-agents>=1.2.0b6` (preview SDK).

### A2A (Agent-to-Agent) Tools

EZ-Agent supports connecting to other A2A-compliant agents as tools. This enables multi-agent orchestration where your agent can delegate tasks to specialized agents.

```yaml
tools:
  # Connect to another A2A agent
  - name: research_agent
    type: agent
    description: A specialized research agent for information gathering
    agent_endpoint: https://research-agent.example.com  # A2A server URL
    headers:                 # Optional: custom headers for authentication
      Authorization: "Bearer ${AGENT_API_KEY}"
```

**How it works**:
1. A2A tools are registered as function tools with an `a2a_` prefix (e.g., `a2a_research_agent`)
2. When the model calls an A2A function, the request is sent to the remote agent via the [A2A protocol](https://a2a-protocol.org/latest/specification/)
3. The response is returned to your agent as a tool result
4. Supports both REST (`/v1/message:send`) and JSON-RPC bindings

**Dependencies**: A2A tools require the `a2a-sdk` package (automatically installed).

## TLS Support

Run agents with TLS in production:

```bash
ezagent run -c my-agent.yaml -m http \
  --tls-cert /etc/tls/tls.crt \
  --tls-key /etc/tls/tls.key \
  --port 8443
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src tests

# Run type checker
mypy src
```

## Architecture

```
src/ez_agent/
├── cli/          # Typer CLI commands
├── config/       # Pydantic configuration models
├── core/         # Agent runtime, task, conversation
├── providers/    # LLM provider implementations
├── storage/      # Task and conversation storage
├── tools/        # Tool registry and execution
├── middleware/   # Request/response middleware
├── a2a/          # A2A protocol server
└── runtime/      # Terminal and HTTP runners
```

## License

MIT License - see [LICENSE](LICENSE) for details.
