# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.3] - 2025-12-03

### Changed
- Simplified `RequestLogs` constructor: removed `json_payload` parameter (now always initialized as `None`)
- `flush()` now uses stored token instead of framework-specific `request.ctx` reference

### Fixed
- Fixed framework-agnostic context reset in `flush()` - previously only worked with Sanic's `request.ctx`

## [0.2.2] - 2025-12-03

### Changed
- Use array for message accumulation instead of string concatenation for better performance

## [0.2.0] - 2025-12-01

### Changed
- Simplified log output format: logs now concatenated in `message` field with timestamp
- Non-request context logs now output as plain text instead of JSON
- Message format: `\n{timestamp}\t{level}\t{message}`

### Removed
- Removed `lines` array from JSON output (replaced with concatenated `message`)
- Removed FastAPI error handler integration (`add_error_handler`)
- Removed `examples/` directory

## [0.1.0] - 2025-11-28

### Added
- Initial release
- `CloudLoggingHandler` for structured JSON logging compatible with Google Cloud Logging
- Request tracing support via `X-Cloud-Trace-Context` header
- Log aggregation per request using context variables
- Severity level tracking (highest severity wins)
- Support for custom JSON encoders (e.g., ujson)
- Type hints and py.typed marker for type checking support

### Features
- Zero external dependencies for core handler
- Optional ujson support for better performance
