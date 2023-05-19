"""
google cloud logging tracing
구조화된 로깅
https://cloud.google.com/logging/docs/structured-logging?hl=ko
"""
import json
import logging
import sys

from contextvars import ContextVar


class RequestLogs:
    def __init__(self, request, json_payload):
        self.request = request
        self.json_payload = json_payload


class CloudLoggingHandler(logging.StreamHandler):
    def __init__(self, trace_header_name=None, json_impl=None, project: str = None):
        super().__init__(stream=sys.stdout)
        self.trace_header_name = trace_header_name
        if json_impl:
            self.json = json_impl
        else:
            self.json = json

        self.project = project

    REQUEST_ID_CTX_KEY = "request_id"

    _request_ctx_var: ContextVar[RequestLogs] = ContextVar(
        REQUEST_ID_CTX_KEY, default=None
    )

    def get_request(self) -> RequestLogs:
        return self._request_ctx_var.get()

    def set_request(self, request: RequestLogs):
        return self._request_ctx_var.set(request)

    def reset_request(self, request_id):
        self._request_ctx_var.reset(request_id)

    def emit(self, record):
        """
        Emit a record.

        If a formatter is specified, it is used to format the record.
        The record is then written to the stream with a trailing newline.  If
        exception information is present, it is formatted using
        traceback.print_exception and appended to the stream.  If the stream
        has an 'encoding' attribute, it is used to determine how to do the
        output to the stream.
        """
        try:
            msg = self.format(record)
            # issue 35046: merged two stream.writes into one.

            request_log = self.get_request()
            if not request_log:
                json_payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "pathname": record.filename,
                    "lineno": record.lineno,
                    "process": record.process,
                }

                trace = None
                span = None
                json_payload["lines"] = [
                    {
                        "pathname": record.filename,
                        "lineno": record.lineno,
                        "message": msg,
                    }
                ]
                self.stream.write(self.json.dumps(json_payload) + self.terminator)
                return

            request = request_log.request
            if not request_log.json_payload:
                request_log.json_payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "process": record.process,
                }

                trace = None
                span = None
                if request:
                    request_log.json_payload["message"] = str(request.url)

                    if self.trace_header_name.lower() in request.headers.keys():
                        # trace can be formatted as "X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE"
                        raw_trace = request.headers.get(self.trace_header_name).split(
                            "/"
                        )
                        trace = raw_trace[0]
                        if len(raw_trace) > 1:
                            span = raw_trace[1].split(";")[0]

                    if trace:
                        request_log.json_payload[
                            "logging.googleapis.com/trace"
                        ] = f"projects/{self.project}/traces/{trace}"
                    if span:
                        request_log.json_payload["logging.googleapis.com/spanId"] = span

                request_log.json_payload["lines"] = [
                    {
                        "pathname": record.filename,
                        "lineno": record.lineno,
                        "message": msg,
                    }
                ]
            else:
                cur_level = getattr(logging, record.levelname)
                prev_level = getattr(logging, request_log.json_payload["severity"])
                if cur_level > prev_level:
                    request_log.json_payload["severity"] = record.levelname

                request_log.json_payload["lines"].append(
                    {
                        "pathname": record.filename,
                        "lineno": record.lineno,
                        "message": msg,
                    }
                )

            self.set_request(request_log)

        except RecursionError:  # See issue 36272
            raise
        except Exception as e:
            self.handleError(record)

    def flush(self):
        """
        Ensure all logging output has been flushed.

        This version does nothing and is intended to be implemented by
        subclasses.
        """
        request_log = self.get_request()
        if request_log:
            log = request_log.json_payload
            self.stream.write(self.json.dumps(log) + self.terminator)

            request = request_log.request
            if hasattr(request.state, "token"):
                self.reset_request(request.state.token)
