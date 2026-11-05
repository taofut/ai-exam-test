import json

from materialops.config import CONTRACTS_ROOT

CODES = json.loads((CONTRACTS_ROOT / "errors.json").read_text(encoding="utf-8"))


class AppError(Exception):
    def __init__(self, code: str, message: str, *, details: list[dict] | None = None):
        self.code = code
        self.message = message
        self.details = details
        self.status_code = CODES[code]
        super().__init__(message)


def pending(stage: str = "业务"):
    raise AppError("NOT_IMPLEMENTED", f"{stage}服务待考生实现；本次请求未执行业务写入。")

