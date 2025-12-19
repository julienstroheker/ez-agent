"""Example tools for EZ-Agent demonstrations."""

from datetime import datetime

from ez_agent.tools import tool


@tool()
def get_weather(city: str, units: str = "celsius") -> str:
    """
    Get the current weather for a city.

    Args:
        city: The city name to get weather for.
        units: Temperature units - celsius or fahrenheit.

    Returns:
        Weather information as a formatted string.
    """
    # This is a mock implementation
    # In production, integrate with a real weather API
    mock_weather = {
        "new york": {"temp": 22, "condition": "Partly Cloudy", "humidity": 65},
        "london": {"temp": 15, "condition": "Rainy", "humidity": 80},
        "tokyo": {"temp": 28, "condition": "Sunny", "humidity": 55},
        "paris": {"temp": 18, "condition": "Cloudy", "humidity": 70},
    }

    city_lower = city.lower()
    if city_lower in mock_weather:
        weather = mock_weather[city_lower]
        temp = weather["temp"]
        if units == "fahrenheit":
            temp = int(temp * 9 / 5 + 32)
            unit_symbol = "°F"
        else:
            unit_symbol = "°C"

        return (
            f"Weather in {city.title()}:\n"
            f"  Temperature: {temp}{unit_symbol}\n"
            f"  Condition: {weather['condition']}\n"
            f"  Humidity: {weather['humidity']}%"
        )
    else:
        return f"Weather data not available for {city}. Try: New York, London, Tokyo, or Paris."


@tool()
def calculate(expression: str) -> str:
    """
    Evaluate a mathematical expression safely.

    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2 * 3").

    Returns:
        The result of the calculation as a string.
    """
    # Only allow safe characters for basic math
    allowed_chars = set("0123456789+-*/.() ")
    if not all(c in allowed_chars for c in expression):
        return "Error: Expression contains invalid characters. Only numbers and basic operators (+, -, *, /, .) are allowed."

    try:
        # Evaluate with no builtins for safety
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except ZeroDivisionError:
        return "Error: Division by zero"
    except SyntaxError:
        return "Error: Invalid expression syntax"
    except Exception as e:
        return f"Error: {e}"


@tool(name="current_time", description="Get the current date and time")
def get_current_time() -> str:
    """
    Get the current date and time.

    Returns:
        Current date and time in a human-readable format.
    """
    now = datetime.now()
    return f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')} (local time)"


@tool()
async def async_example(query: str) -> str:
    """
    An example async tool.

    Args:
        query: A query string to process.

    Returns:
        Processed result.
    """
    import asyncio
    # Simulate async operation
    await asyncio.sleep(0.1)
    return f"Processed query: {query}"
