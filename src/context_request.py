from contextvars import ContextVar

from starlette.requests import Request

REQUEST_ID_CTX_KEY = "request_id"

_request_ctx_var: ContextVar[Request] = ContextVar(REQUEST_ID_CTX_KEY, default=None)


def get_request() -> Request:
    return _request_ctx_var.get()


def set_request(request):
    return _request_ctx_var.set(request)


def reset_request(request_id):
    _request_ctx_var.reset(request_id)
