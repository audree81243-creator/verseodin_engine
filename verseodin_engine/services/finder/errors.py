class FindError(RuntimeError):
    """Raised when a URL finding operation fails."""

    def __init__(self, message="An error occurred during URL finding", url=None):
        super().__init__(message)
        self.url = url

    def __str__(self):
        if self.url:
            return f"{super().__str__()} (URL: {self.url})"
        return super().__str__()
