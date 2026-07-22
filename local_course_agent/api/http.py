from __future__ import annotations

import cgi
import json
from http import HTTPStatus
from typing import Any, BinaryIO, Mapping


JSON_CONTENT_TYPE = "application/json; charset=utf-8"
SSE_CONTENT_TYPE = "text/event-stream; charset=utf-8"
NDJSON_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"


class ClientDisconnected(Exception):
    pass


def read_json_body(headers: Mapping[str, str], body: BinaryIO) -> dict:
    length = parse_content_length(headers)
    raw = body.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def read_request_payload(
    headers: Mapping[str, str],
    body: BinaryIO,
    *,
    max_total_upload_bytes: int,
) -> tuple[dict, list[dict]]:
    content_type = headers.get("Content-Type", "")
    if not content_type.startswith("multipart/form-data"):
        return read_json_body(headers, body), []
    return read_multipart_payload(headers, body, max_total_upload_bytes=max_total_upload_bytes)


def read_multipart_payload(
    headers: Mapping[str, str],
    body: BinaryIO,
    *,
    max_total_upload_bytes: int,
) -> tuple[dict, list[dict]]:
    content_type = headers.get("Content-Type", "")
    length = parse_content_length(headers)
    if length > max_total_upload_bytes:
        limit_mb = max_total_upload_bytes // (1024 * 1024)
        raise ValueError(f"上传内容过大，总大小不能超过 {limit_mb} MB")
    form = cgi.FieldStorage(
        fp=body,
        headers=headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(length),
        },
    )
    fields: dict[str, Any] = {}
    uploads: list[dict] = []
    for key in form.keys():
        values = form[key]
        if not isinstance(values, list):
            values = [values]
        for item in values:
            if item.filename:
                uploads.append({"filename": item.filename, "content": item.file.read()})
            else:
                fields[key] = item.value
    return fields, uploads


def json_response_body(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def json_response_headers(raw: bytes) -> list[tuple[str, str]]:
    return [
        ("Content-Type", JSON_CONTENT_TYPE),
        ("Content-Length", str(len(raw))),
    ]


def error_payload(message: str) -> dict:
    return {"ok": False, "error": message}


def stream_response_headers(stream_format: str = "sse") -> list[tuple[str, str]]:
    content_type = SSE_CONTENT_TYPE if stream_format == "sse" else NDJSON_CONTENT_TYPE
    return [
        ("Content-Type", content_type),
        ("X-Content-Type-Options", "nosniff"),
        ("Cache-Control", "no-cache, no-transform"),
        ("X-Accel-Buffering", "no"),
        ("Transfer-Encoding", "chunked"),
    ]


def stream_event_payload(event: Any, stream_format: str = "sse") -> bytes:
    payload = json.dumps(event, ensure_ascii=False)
    if stream_format == "sse":
        return f"data: {payload}\n\n".encode("utf-8")
    return f"{payload}\n".encode("utf-8")


def chunk_frame(raw: bytes) -> bytes:
    return f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n"


def stream_event_frame(event: Any, stream_format: str = "sse") -> bytes:
    return chunk_frame(stream_event_payload(event, stream_format))


def stream_end_frame() -> bytes:
    return b"0\r\n\r\n"


def write_stream_event(writer: BinaryIO, event: Any, stream_format: str = "sse") -> bool:
    try:
        writer.write(stream_event_frame(event, stream_format))
        writer.flush()
    except (BrokenPipeError, ConnectionResetError):
        raise ClientDisconnected
    return True


def write_stream_end(writer: BinaryIO) -> bool:
    try:
        writer.write(stream_end_frame())
        writer.flush()
    except (BrokenPipeError, ConnectionResetError):
        return False
    return True


def parse_content_length(headers: Mapping[str, str]) -> int:
    raw = headers.get("Content-Length", "0") or "0"
    return int(raw)


def send_json_response(handler: Any, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    raw = json_response_body(payload)
    handler.send_response(status)
    for name, value in json_response_headers(raw):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(raw)


def begin_chunked_stream(handler: Any, stream_format: str = "sse") -> None:
    handler.send_response(HTTPStatus.OK)
    for name, value in stream_response_headers(stream_format):
        handler.send_header(name, value)
    handler.end_headers()
