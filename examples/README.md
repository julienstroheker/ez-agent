# EZ-Agent Examples

This directory contains example agent configurations demonstrating different EZ-Agent capabilities.

## Examples

| Example | Description |
|---------|-------------|
| [simple-agent.yaml](simple-agent.yaml) | Basic conversational agent - start here |
| [tool-agent.yaml](tool-agent.yaml) | Agent with Python function tools |
| [mcp-agent.yaml](mcp-agent.yaml) | Agent with MCP (Model Context Protocol) tools |
| [a2a-agent.yaml](a2a-agent.yaml) | Multi-agent orchestration with A2A protocol |

## Prerequisites

1. **Azure AI Foundry**: Set up an Azure AI Foundry project
2. **Environment Variable**: Set `AZURE_AI_ENDPOINT` to your project endpoint
3. **Authentication**: Use Azure CLI (`az login`) or set up managed identity

```bash
export AZURE_AI_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
```

## Running Examples

### Terminal Mode (Interactive)

```bash
# Simple agent
ezagent run -c examples/simple-agent.yaml -m terminal

# Agent with tools
ezagent run -c examples/tool-agent.yaml -m terminal
```

### HTTP Mode (Production)

```bash
# Run as HTTP server
ezagent run -c examples/simple-agent.yaml -m http --port 8000

# With TLS
ezagent run -c examples/simple-agent.yaml -m http --port 8443 \
  --tls-cert /path/to/cert.pem \
  --tls-key /path/to/key.pem
```

## Validation

Validate configuration without running:

```bash
ezagent validate -c examples/simple-agent.yaml
```

## Custom Tools

The [tools.py](tools.py) file contains example Python functions used by `tool-agent.yaml`:

- `get_weather(city)` - Returns mock weather data
- `calculate(expression)` - Evaluates math expressions
- `get_current_time()` - Returns current date/time

To create your own tools, define Python functions with type hints and docstrings:

```python
def my_tool(param1: str, param2: int = 10) -> str:
    """Description of what the tool does.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Description of return value
    """
    return f"Result: {param1}, {param2}"
```

Then reference it in your agent config:

```yaml
tools:
  - name: my_tool
    type: function
    module: my_module
    function: my_tool
```
