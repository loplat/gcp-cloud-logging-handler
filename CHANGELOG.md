# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2024-XX-XX

### Added
- Initial release
- `CloudLoggingHandler` for structured JSON logging compatible with Google Cloud Logging
- Request tracing support via `X-Cloud-Trace-Context` header
- Log aggregation per request using context variables
- Severity level tracking (highest severity wins)
- FastAPI integration with `add_error_handler`
- Support for custom JSON encoders (e.g., ujson)
- Type hints and py.typed marker for type checking support

### Features
- Zero external dependencies for core handler
- Optional FastAPI integration
- Optional ujson support for better performance
