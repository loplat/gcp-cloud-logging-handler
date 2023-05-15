"""
google cloud logging tracing
구조화된 로깅
https://cloud.google.com/logging/docs/structured-logging?hl=ko
"""
import json
import logging
import sys

from src.context_request import get_request


class CloudLoggingHandler(logging.StreamHandler):
    def __init__(self, trace_header_name=None, json_impl=None, project: str = None):
        super().__init__(stream=sys.stdout)
        self.trace_header_name = trace_header_name
        if json_impl:
            self.json = json_impl
        else:
            self.json = json

        self.project = project

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
            stream = self.stream
            # issue 35046: merged two stream.writes into one.
            json_payload = {
                "severity": record.levelname,
                "name": record.name,
                "message": msg,
                "pathname": record.filename,
                "lineno": record.lineno,
                "process": record.process,
            }

            trace = None
            span = None
            request = get_request()
            if request and self.trace_header_name.lower() in request.headers.keys():
                # trace can be formatted as "X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE"
                raw_trace = request.headers.get(self.trace_header_name).split("/")
                trace = raw_trace[0]
                if len(raw_trace) > 1:
                    span = raw_trace[1].split(";")[0]
            if trace:
                json_payload[
                    "logging.googleapis.com/trace"
                ] = f"projects/{self.project}/traces/{trace}"
            if span:
                json_payload["logging.googleapis.com/spanId"] = span

            stream.write(self.json.dumps(json_payload) + self.terminator)
            self.flush()
        except RecursionError:  # See issue 36272
            raise
        except Exception as e:
            self.handleError(record)
