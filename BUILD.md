# Build & Development Guide

Quick reference for local development and CI/CD pipelines.

## Prerequisites

- Python 3.11+
- pip or uv package manager

## Quick Start

```bash
# Clone the repository
git clone https://github.com/julienstroheker/ez-agent.git
cd ez-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

## Commands

### Run Tests

```bash
# All tests with coverage
pytest

# Specific test file
pytest tests/test_config.py

# With verbose output
pytest -v

# Skip slow tests
pytest -m "not slow"
```

### Linting & Formatting

```bash
# Check code style
ruff check src tests

# Auto-fix issues
ruff check --fix src tests

# Format code
ruff format src tests
```

### Type Checking

```bash
mypy src
```

### Build Package

```bash
# Build wheel and sdist
pip install build
python -m build
```

### Build Docker Image

```bash
# Build base image
docker build -t ez-agent:latest .

# Build with version tag
docker build -t ez-agent:v1.0.0 .
```

## CI/CD Pipeline Commands

For use in GitHub Actions, Azure DevOps, or other CI systems:

```bash
# Install dependencies (CI)
pip install -e ".[dev]"

# Run all quality checks
ruff check src tests
mypy src
pytest --cov=ez_agent --cov-report=xml

# Build artifacts
python -m build
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_AI_ENDPOINT` | Azure AI Foundry project endpoint | Yes (runtime) |
| `APP_INSIGHTS_CONNECTION_STRING` | Application Insights for tracing | No |

## Project Structure

```
ez-agent/
├── src/ez_agent/      # Source code
├── tests/             # Test suite
├── examples/          # Example configurations
├── charts/            # Helm charts for Kubernetes
├── Dockerfile         # Container image
├── pyproject.toml     # Package configuration
└── BUILD.md           # This file
```

## Release Checklist

1. Update version in `pyproject.toml`
2. Run full test suite: `pytest`
3. Run linting: `ruff check src tests`
4. Run type check: `mypy src`
5. Build package: `python -m build`
6. Build Docker image: `docker build -t ez-agent:vX.Y.Z .`
7. Tag release: `git tag vX.Y.Z`
