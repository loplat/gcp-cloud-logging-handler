import logging

from fastapi import FastAPI, Request, HTTPException
from starlette.responses import JSONResponse


def add_error_handler(app: FastAPI, logging_handler=None) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_type_error_handler(request: Request, e: HTTPException):
        msg = {"error": e.__class__.__name__, "detail": e.detail}
        if e.status_code >= 500:
            logging.exception(e)
        elif e.status_code >= 400:
            if hasattr(request.state, "log_messages"):
                logging.debug(request.state.log_messages)
            logging.warning(msg)

        if logging_handler:
            logging_handler.flush()

        return JSONResponse(msg, status_code=e.status_code)

    @app.exception_handler(Exception)
    async def exception_handler(request: Request, e: Exception):
        if hasattr(request.state, "log_messages"):
            logging.debug(request.state.log_messages)
        logging.exception(e)

        if logging_handler:
            logging_handler.flush()

        return JSONResponse(
            {"error": e.__class__.__name__, "detail": str(e)}, status_code=500
        )
