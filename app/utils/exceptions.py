class RetryableError(Exception):
    """Triggers job retry"""
    pass

class PermanentError(Exception):
    """Marks batch as failed permanently"""
    pass

class OpenAIError(RetryableError):
    """Exception for OpenAI-related errors."""
    pass