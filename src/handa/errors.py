"""Errors the API can show to a person without a stack trace."""


class DeskError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProviderError(DeskError):
    def __init__(self, message: str):
        super().__init__(message, status_code=502)
