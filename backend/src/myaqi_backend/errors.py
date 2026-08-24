from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, title: str, detail: str, code: str) -> None:
        super().__init__(detail)
        self.status = status
        self.title = title
        self.detail = detail
        self.code = code
