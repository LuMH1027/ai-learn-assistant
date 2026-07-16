import json
import unittest
from unittest import mock

from local_course_agent.web_search import McpWebSearchClient, should_search_web


class FakeResponse:
    def __init__(self, payload, headers=None, status=200):
        self.payload = payload
        self.headers = headers or {"Content-Type": "application/json"}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        if self.payload is None:
            return b""
        return json.dumps(self.payload).encode("utf-8")


class WebSearchTest(unittest.TestCase):
    def test_search_decision_prefers_sufficient_local_evidence(self):
        sufficient = {"retrieval_quality": "sufficient", "citations": [{"file_name": "教材.md"}]}

        self.assertFalse(should_search_web("解释页表的作用", sufficient))
        self.assertTrue(should_search_web("请联网查一下页表的最新研究", sufficient))
        self.assertTrue(should_search_web("总结 2026 年虚拟内存研究", sufficient))
        self.assertTrue(should_search_web("解释量子纠缠", {"retrieval_quality": "none", "citations": []}))
        self.assertTrue(should_search_web("比较两种算法", {"retrieval_quality": "partial", "citations": [{}]}))

    def test_streamable_http_mcp_search_runs_lifecycle_and_returns_citable_sources(self):
        responses = [
            FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "search", "version": "1"},
                    },
                },
                headers={"Content-Type": "application/json", "Mcp-Session-Id": "session-1"},
            ),
            FakeResponse(None, status=202),
            FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "structuredContent": {
                            "results": [
                                {
                                    "title": "Virtual memory",
                                    "url": "https://example.edu/vm",
                                    "content": "Virtual memory separates logical and physical addresses.",
                                }
                            ]
                        },
                        "isError": False,
                    },
                }
            ),
        ]
        client = McpWebSearchClient(
            {
                "enabled": True,
                "mcp_url": "https://search.example/mcp",
                "tool_name": "web_search",
                "query_argument": "query",
                "max_results_argument": "max_results",
                "max_results": 4,
            }
        )

        with mock.patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            sources = client.search("virtual memory")

        self.assertEqual(sources[0]["source_type"], "web")
        self.assertEqual(sources[0]["url"], "https://example.edu/vm")
        self.assertEqual(sources[0]["file_name"], "Virtual memory")
        requests = [json.loads(call.args[0].data.decode("utf-8")) for call in urlopen.call_args_list]
        self.assertEqual([request["method"] for request in requests], [
            "initialize", "notifications/initialized", "tools/call",
        ])
        self.assertEqual(requests[-1]["params"]["arguments"]["query"], "virtual memory")
        self.assertEqual(requests[-1]["params"]["arguments"]["max_results"], 4)
        self.assertEqual(urlopen.call_args_list[-1].args[0].headers["Mcp-session-id"], "session-1")

    def test_search_discards_results_without_http_sources(self):
        client = McpWebSearchClient({"enabled": True, "mcp_url": "https://search.example/mcp"})

        sources = client.normalize_sources({
            "structuredContent": {
                "results": [
                    {"title": "No URL", "content": "uncitable"},
                    {"title": "Unsafe", "url": "file:///tmp/private", "content": "private"},
                ]
            }
        })

        self.assertEqual(sources, [])

    def test_search_parses_citable_title_url_highlight_text_blocks(self):
        client = McpWebSearchClient({"enabled": True, "mcp_url": "https://search.example/mcp"})

        sources = client.normalize_sources({
            "content": [{
                "type": "text",
                "text": (
                    "Title: Python 3.14\n"
                    "URL: https://python.org/3.14\n"
                    "Published: 2025-10-07\n"
                    "Highlights:\nReleased in October.\n\n---\n\n"
                    "Title: Documentation\n"
                    "URL: https://docs.python.org/3.14\n"
                    "Highlights:\nOfficial documentation."
                ),
            }]
        })

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["file_name"], "Python 3.14")
        self.assertIn("Released in October", sources[0]["quote"])


if __name__ == "__main__":
    unittest.main()
