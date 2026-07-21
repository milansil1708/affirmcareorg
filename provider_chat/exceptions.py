class AIIntegrationError(Exception):
    """Base exception for safe AI integration failures."""


class AIConfigurationError(AIIntegrationError):
    pass


class AITemporaryError(AIIntegrationError):
    pass


class AIResponseError(AIIntegrationError):
    pass


class AIRefusalError(AIIntegrationError):
    pass


class ConversationNotFoundError(Exception):
    pass


class ConversationStateError(Exception):
    pass
