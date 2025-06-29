class ExpectedError(Exception):
    """An expected error that can be reported without a traceback."""


class DeckSyntaxError(ExpectedError):
    """Syntax error in a .deck file."""

    def __init__(self, message: str, source_path: str, line_number: int):
        self.message = message
        self.source_path = source_path
        self.line_number = line_number

    def __str__(self):
        return f"Error in {self.where()}: {self.message}"

    def where(self):
        return f"{self.source_path}, line {self.line_number}"
