"""Provider registry for managing provider instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ez_agent.config.models import ConfigurationSettings, ProviderType
from ez_agent.providers.base import IProvider, ProviderError

if TYPE_CHECKING:
    pass


class ProviderRegistry:
    """
    Registry for LLM provider implementations.

    Allows registration of new providers and instantiation based on configuration.
    """

    _providers: dict[ProviderType, type[IProvider]] = {}

    @classmethod
    def register(cls, provider_type: ProviderType) -> type[IProvider]:
        """
        Decorator to register a provider implementation.

        Usage:
            @ProviderRegistry.register(ProviderType.AZURE_FOUNDRY)
            class AzureFoundryProvider(IProvider):
                ...
        """
        def decorator(provider_class: type[IProvider]) -> type[IProvider]:
            cls._providers[provider_type] = provider_class
            return provider_class
        return decorator  # type: ignore

    @classmethod
    def get(cls, config: ConfigurationSettings) -> IProvider:
        """
        Get a provider instance for the given configuration.

        Args:
            config: Configuration settings containing provider type and options.

        Returns:
            Initialized provider instance.

        Raises:
            ProviderError: If the provider type is not registered.
        """
        provider_type = config.provider

        if provider_type not in cls._providers:
            # Try to import the provider module to trigger registration
            cls._import_provider(provider_type)

        if provider_type not in cls._providers:
            available = [p.value for p in cls._providers.keys()]
            raise ProviderError(
                f"Provider '{provider_type.value}' is not registered. "
                f"Available providers: {available}",
                provider=provider_type.value,
            )

        provider_class = cls._providers[provider_type]
        return provider_class(config)

    @classmethod
    def _import_provider(cls, provider_type: ProviderType) -> None:
        """Import provider module to trigger registration."""
        try:
            if provider_type == ProviderType.AZURE_FOUNDRY:
                from ez_agent.providers import azure_foundry  # noqa: F401
            elif provider_type == ProviderType.LOCAL:
                from ez_agent.providers import local  # noqa: F401
        except ImportError:
            pass  # Provider module not available

    @classmethod
    def available_providers(cls) -> list[ProviderType]:
        """Return list of registered provider types."""
        return list(cls._providers.keys())


def get_provider(config: ConfigurationSettings) -> IProvider:
    """
    Convenience function to get a provider instance.

    Args:
        config: Configuration settings.

    Returns:
        Provider instance.
    """
    return ProviderRegistry.get(config)
