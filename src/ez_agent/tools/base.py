"""Base tool interface and decorators."""

from __future__ import annotations

import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, get_type_hints

F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    """Exception raised when tool execution fails."""

    def __init__(self, message: str, tool_name: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.cause = cause


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    """Complete definition of a tool for LLM consumption."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON schema format for LLM tools."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


class ITool(ABC):
    """Abstract interface for a tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        ...

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Get the tool definition for LLM consumption."""
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the tool with the given arguments.

        Args:
            **kwargs: Tool arguments.

        Returns:
            Tool result as a JSON string.

        Raises:
            ToolError: If execution fails.
        """
        ...


def _python_type_to_json_type(python_type: type | None) -> str:
    """Convert Python type annotation to JSON schema type."""
    if python_type is None:
        return "string"

    type_mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    # Handle Optional types and other typing constructs
    origin = getattr(python_type, "__origin__", None)
    if origin is not None:
        # Handle Union types (including Optional)
        if origin is type(None):
            return "string"
        # Handle list[T]
        if origin is list:
            return "array"
        # Handle dict[K, V]
        if origin is dict:
            return "object"

    return type_mapping.get(python_type, "string")


def _parse_docstring(docstring: str | None) -> tuple[str, dict[str, str]]:
    """
    Parse a docstring to extract description and parameter descriptions.

    Returns:
        Tuple of (main_description, {param_name: param_description})
    """
    if not docstring:
        return "", {}

    lines = docstring.strip().split("\n")
    description_lines: list[str] = []
    param_descriptions: dict[str, str] = {}

    in_args_section = False
    current_param: str | None = None
    current_param_desc: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Check for Args: section
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args_section = True
            continue

        # Check for other sections that end Args
        if stripped.lower() in ("returns:", "raises:", "yields:", "examples:", "note:", "notes:"):
            in_args_section = False
            if current_param:
                param_descriptions[current_param] = " ".join(current_param_desc).strip()
                current_param = None
                current_param_desc = []
            continue

        if in_args_section:
            # Check if this is a new parameter
            if ":" in stripped and not stripped.startswith(" "):
                # Save previous parameter
                if current_param:
                    param_descriptions[current_param] = " ".join(current_param_desc).strip()

                # Parse new parameter
                parts = stripped.split(":", 1)
                # Handle "param_name (type): description" format
                param_part = parts[0].strip()
                if " " in param_part:
                    param_name = param_part.split()[0]
                else:
                    param_name = param_part

                current_param = param_name
                current_param_desc = [parts[1].strip()] if len(parts) > 1 else []
            elif current_param and stripped:
                # Continuation of current parameter description
                current_param_desc.append(stripped)
        else:
            if not in_args_section and stripped:
                description_lines.append(stripped)

    # Save last parameter
    if current_param:
        param_descriptions[current_param] = " ".join(current_param_desc).strip()

    return " ".join(description_lines), param_descriptions


class FunctionTool(ITool):
    """
    A tool that wraps a Python function.

    Uses docstrings for descriptions and type hints for parameter schemas.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Initialize a function tool.

        Args:
            func: The function to wrap.
            name: Optional custom name (defaults to function name).
            description: Optional custom description (defaults to docstring).
        """
        self._func = func
        self._name = name or func.__name__
        self._is_async = inspect.iscoroutinefunction(func)

        # Parse function metadata
        self._signature = inspect.signature(func)
        self._type_hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}

        # Parse docstring
        doc_description, self._param_descriptions = _parse_docstring(func.__doc__)
        self._description = description or doc_description or f"Execute {self._name}"

    @property
    def name(self) -> str:
        """Return the tool name."""
        return self._name

    @property
    def description(self) -> str:
        """Return the tool description."""
        return self._description

    def get_definition(self) -> ToolDefinition:
        """Get the tool definition."""
        parameters: list[ToolParameter] = []

        for param_name, param in self._signature.parameters.items():
            # Skip self/cls for methods
            if param_name in ("self", "cls"):
                continue

            # Get type hint
            python_type = self._type_hints.get(param_name)
            json_type = _python_type_to_json_type(python_type)

            # Get description from docstring
            param_desc = self._param_descriptions.get(param_name, f"The {param_name} parameter")

            # Check if required (no default value)
            required = param.default is inspect.Parameter.empty

            parameters.append(ToolParameter(
                name=param_name,
                type=json_type,
                description=param_desc,
                required=required,
                default=None if required else param.default,
            ))

        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters=parameters,
        )

    async def execute(self, **kwargs: Any) -> str:
        """Execute the wrapped function."""
        try:
            if self._is_async:
                result = await self._func(**kwargs)
            else:
                result = self._func(**kwargs)

            # Convert result to JSON string
            if isinstance(result, str):
                return result
            return json.dumps(result, default=str)

        except Exception as e:
            raise ToolError(
                message=f"Tool execution failed: {e}",
                tool_name=self._name,
                cause=e,
            )


def tool(
    name: str | None = None,
    description: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator to mark a function as a tool.

    Usage:
        @tool()
        def get_weather(city: str) -> str:
            '''Get the current weather for a city.

            Args:
                city: The city name to get weather for.

            Returns:
                Weather information as a string.
            '''
            return f"Weather in {city}: Sunny, 72°F"

        @tool(name="custom_name", description="Custom description")
        async def my_tool(param: int) -> dict:
            return {"result": param * 2}

    Args:
        name: Optional custom tool name.
        description: Optional custom description.

    Returns:
        Decorator function.
    """
    def decorator(func: F) -> F:
        # Store metadata on the function for later registration
        func._tool_metadata = {  # type: ignore
            "name": name,
            "description": description,
        }
        return func

    return decorator
