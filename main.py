import asyncio
import logging
import os

import uvicorn
from aiohttp import TCPConnector
from fastapi import FastAPI, Request
from starlette import status

from src import http_connection
from src.cloud_logging_handler import CloudLoggingHandler
from src.context_request import set_request, reset_request
from src.error_handler import add_error_handler

app = FastAPI()

add_error_handler(app)

cloud_handler = CloudLoggingHandler(
    trace_header_name="X-Cloud-Trace-Context", json_impl=ujson, project=os.environ["GCP_PROJECT"]
)
cloud_logging = logging.getLogger("root")
cloud_logging.addHandler(cloud_handler)
cloud_logging.setLevel(logging.DEBUG)


@app.on_event("startup")
async def startup_event():
    pass


@app.on_event("shutdown")
async def shutdown_event():
    pass

@app.middleware("http")
async def set_request_context(request: Request, call_next):
    """request context middleware
    마지막에 선언된 middleware 가 request 를 먼저 consume하고 제일 마지막에 response 를 handling 한다.
    logging 시 trace id 를 사용하므로, request context 처음부터 끝까지 유지하기 위해서는
    이 middleware 는 항상 제일 마지막에 위치해야한다."""
    request_id = set_request(request)
    response = await call_next(request)
    reset_request(request_id)
    return response


@app.get("/", status_code=status.HTTP_200_OK)
async def get(request: Request):
    logging.debug("debug")
    logging.info("info")
    logging.warning("warning")
    logging.error("error")
    logging.exception("exception")
    return


if __name__ == "__main__":
    # local debugging 용도로 사용하기 위한 코드
    uvicorn.run(app, host="0.0.0.0", port=8080)
