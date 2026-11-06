from fastapi.responses import JSONResponse

from brainseg_inference.logging import correlation_id


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(error: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {"code": error.code, "message": error.message},
            "correlationId": correlation_id.get(),
        },
    )
