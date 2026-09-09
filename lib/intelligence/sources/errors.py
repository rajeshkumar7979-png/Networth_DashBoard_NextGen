# -------------------------------------------------
# Intelligence Data Gateway — error taxonomy.
# Pure module. Every provider failure maps to one of these; callers convert to
# an unavailable SourceResult so a failed provider can never produce a
# successful evidence record.
# -------------------------------------------------


class GatewayError(Exception):
    """Base class for all intelligence-gateway provider errors."""


class ProviderConfigMissing(GatewayError):
    """Required configuration (e.g. an API key) is absent. No network call."""


class ProviderUnavailable(GatewayError):
    """Network/HTTP failure contacting a provider."""


class ProviderTimeout(ProviderUnavailable):
    """The provider did not respond within the configured timeout."""


class ProviderMalformed(GatewayError):
    """The provider answered with an unparseable/invalid payload."""