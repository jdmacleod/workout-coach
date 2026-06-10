class InferenceError(Exception):
    """Raised when inference fails for any reason."""


class InferenceTimeoutError(InferenceError):
    """Raised when the provider exceeds the response timeout."""


class InferenceParseError(InferenceError):
    """Raised when the provider response cannot be parsed as expected JSON."""
