"""Configuration loading and validation utilities."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ez_agent.config.models import AgentConfig


class ConfigError(Exception):
    """Configuration loading or validation error."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def _expand_env_vars(value: Any) -> Any:
    """
    Recursively expand environment variables in configuration values.

    Supports ${VAR_NAME} syntax with optional default: ${VAR_NAME:-default}
    """
    if isinstance(value, str):
        # Pattern matches ${VAR_NAME} or ${VAR_NAME:-default}
        pattern = r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}"

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.environ.get(var_name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            return match.group(0)  # Keep original if not found and no default

        return re.sub(pattern, replace, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def load_config(config_path: str | Path) -> AgentConfig:
    """
    Load and validate an agent configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Validated AgentConfig instance.

    Raises:
        ConfigError: If the file cannot be read or validation fails.
    """
    path = Path(config_path)

    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    if not path.is_file():
        raise ConfigError(f"Configuration path is not a file: {path}")

    if path.suffix.lower() not in (".yaml", ".yml"):
        raise ConfigError(f"Configuration file must be YAML (.yaml or .yml): {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML syntax: {e}") from e
    except OSError as e:
        raise ConfigError(f"Error reading configuration file: {e}") from e

    if not isinstance(raw_config, dict):
        raise ConfigError("Configuration file must contain a YAML mapping (dictionary)")

    # Expand environment variables
    expanded_config = _expand_env_vars(raw_config)

    try:
        return AgentConfig.model_validate(expanded_config)
    except ValidationError as e:
        errors = [
            {
                "loc": ".".join(str(loc) for loc in err["loc"]),
                "msg": err["msg"],
                "type": err["type"],
            }
            for err in e.errors()
        ]
        raise ConfigError(f"Configuration validation failed: {e.error_count()} error(s)", errors) from e


def validate_config(config_path: str | Path) -> tuple[bool, list[dict[str, Any]]]:
    """
    Validate a configuration file without loading it.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Tuple of (is_valid, list of error dictionaries).
    """
    try:
        load_config(config_path)
        return True, []
    except ConfigError as e:
        return False, e.errors if e.errors else [{"loc": "", "msg": e.message, "type": "config_error"}]
