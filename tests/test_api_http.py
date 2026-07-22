import io
import json
import unittest
from email.message import Message
from unittest import mock

from local_course_agent.api.http import (
    ClientDisconnected,
    chunk_frame,
    error_payload,
    json_response_body,
    json_response_headers,
    read_json_body,
    read_request_payload,
    stream_end_frame,
    stream_event_frame,
    stream_event_payload,
    stream_response_headers,
    write_stream_event,
)


def make_headers(values):
    headers = Message()
    for name, value in values.items():
        headers[name] = value
    return headers


class ApiHttpTest(unittest.TestCase):
    def test_read_json_body_defaults_to_empty_object(self):
        headers = make_headers({})

        self.assertEqual(read_json_body(headers, io.BytesIO()), {})

    def test_read_json_body_decodes_utf8_payload(self):
        raw = json.dumps({"question": "页表是什么"}, ensure_ascii=False).encode("utf-8")
        headers = make_headers({"Content-Length": str(len(raw))})

        self.assertEqual(read_json_body(headers, io.BytesIO(raw)), {"question": "页表是什么"})

    def test_read_request_payload_parses_multipart_fields_and_uploads(self):
        boundary = "course-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="question"\r\n\r\n'
            "解释截图\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="screen.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
            "png-bytes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        headers = make_headers(
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            }
        )

        fields, uploads = read_request_payload(
            headers,
            io.BytesIO(body),
            max_total_upload_bytes=1024 * 1024,
        )

        self.assertEqual(fields, {"question": "解释截图"})
        self.assertEqual(uploads, [{"filename": "screen.png", "content": b"png-bytes"}])

    def test_read_request_payload_rejects_oversized_multipart_before_reading(self):
        headers = make_headers(
            {
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": str(3 * 1024 * 1024),
            }
        )

        with self.assertRaisesRegex(ValueError, "总大小不能超过 1 MB"):
            read_request_payload(headers, io.BytesIO(b""), max_total_upload_bytes=1024 * 1024)

    def test_json_response_helpers_preserve_unicode_and_content_length(self):
        raw = json_response_body({"ok": True, "answer": "你好"})

        self.assertEqual(json.loads(raw.decode("utf-8"))["answer"], "你好")
        self.assertEqual(
            json_response_headers(raw),
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(raw))),
            ],
        )
        self.assertEqual(error_payload("失败"), {"ok": False, "error": "失败"})

    def test_stream_headers_select_sse_or_ndjson_content_type(self):
        self.assertIn(
            ("Content-Type", "text/event-stream; charset=utf-8"),
            stream_response_headers("sse"),
        )
        self.assertIn(
            ("Content-Type", "application/x-ndjson; charset=utf-8"),
            stream_response_headers("ndjson"),
        )
        self.assertIn(("Transfer-Encoding", "chunked"), stream_response_headers("sse"))

    def test_stream_event_frame_uses_chunked_sse_payload(self):
        event = {"type": "delta", "delta": "深度"}
        raw = ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8")

        self.assertEqual(stream_event_payload(event), raw)
        self.assertEqual(chunk_frame(raw), f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n")
        self.assertEqual(stream_event_frame(event), chunk_frame(raw))
        self.assertEqual(stream_end_frame(), b"0\r\n\r\n")

    def test_stream_event_frame_keeps_ndjson_compatibility(self):
        event = {"type": "delta", "delta": "旧"}

        self.assertEqual(
            stream_event_payload(event, "ndjson"),
            (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"),
        )

    def test_write_stream_event_raises_domain_exception_on_disconnect(self):
        writer = mock.Mock()
        writer.write.side_effect = BrokenPipeError

        with self.assertRaises(ClientDisconnected):
            write_stream_event(writer, {"type": "delta"})


if __name__ == "__main__":
    unittest.main()
