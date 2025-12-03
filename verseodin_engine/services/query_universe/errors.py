class QueryUniverseError(RuntimeError):
    """Raised when a query universe operation fails."""

    def __init__(self, message="An error occurred during query universe processing", query=None):
        super().__init__(message)
        self.query = query

    def __str__(self):
        if self.query:
            return f"{super().__str__()} (Query: {self.query})"
        return super().__str__()
