"""Safe domain failures; never include submitted values or database diagnostics."""


class DataError(Exception):
    def __init__(self, status: int, code: str, field: str | None = None) -> None:
        self.status = status
        self.code = code
        self.field = field
        super().__init__(code)
