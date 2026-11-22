class DocAIError(Exception):
    """Raised by Document AI routes; rendered in the contract's common error shape (see main.py)."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.details = status_code, code, message, details
