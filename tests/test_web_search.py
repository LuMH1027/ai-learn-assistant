import json
import unittest
from unittest import mock

from local_course_agent.web_search import (
    McpWebSearchClient,
    create_web_search_client,
    is_underspecified_query,
    should_search_web,
    source_quality,
)
from local_course_agent.web.normalization import normalize_sources
from local_course_agent.web.policy import should_search_web as should_search_web_from_policy
from local_course_agent.web.quality import source_quality as source_quality_from_quality


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
    def test_web_search_facade_keeps_legacy_import_surface(self):
        client = create_web_search_client({"enabled": True, "mcp_url": "https://search.example/mcp"})

        self.assertIsInstance(client, McpWebSearchClient)
        self.assertIs(should_search_web, should_search_web_from_policy)
        self.assertIs(source_quality, source_quality_from_quality)
        self.assertEqual(
            normalize_sources({
                "structuredContent": {
                    "results": [{
                        "title": "Docs",
                        "url": "https://docs.python.org/3/",
                        "content": "Python documentation reference with enough text for ranking.",
                    }]
                }
            })[0]["source_type"],
            "web",
        )

    def test_underspecified_queries_never_trigger_web_search(self):
        missing = {"retrieval_quality": "none", "citations": []}

        for question in ("1", "1、", "?", "一"):
            self.assertTrue(is_underspecified_query(question))
            self.assertFalse(should_search_web(question, missing))

        self.assertFalse(is_underspecified_query("解释数字 1"))
        self.assertFalse(is_underspecified_query("树"))

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

    def test_web_snippets_are_bounded_before_reaching_the_prompt(self):
        client = McpWebSearchClient({"enabled": True, "mcp_url": "https://search.example/mcp"})

        sources = client.normalize_sources({
            "structuredContent": {
                "results": [{
                    "title": "Long result",
                    "url": "https://example.edu/long",
                    "content": "x" * 1000,
                }]
            }
        })

        self.assertEqual(len(sources[0]["quote"]), 360)

    def test_sources_are_ranked_by_citable_quality(self):
        client = McpWebSearchClient({"enabled": True, "mcp_url": "https://search.example/mcp"})

        sources = client.normalize_sources({
            "structuredContent": {
                "results": [
                    {
                        "title": "Blog",
                        "url": "https://random.example/post",
                        "content": "short",
                        "score": 0.99,
                    },
                    {
                        "title": "Official Documentation",
                        "url": "https://docs.python.org/3/tutorial/",
                        "content": "Python official tutorial documentation with enough text to cite clearly in a student answer.",
                        "score": 0.1,
                    },
                ]
            }
        })

        self.assertEqual(sources[0]["url"], "https://docs.python.org/3/tutorial/")
        self.assertGreater(sources[0]["source_quality"], sources[1]["source_quality"])
        self.assertGreater(source_quality("https://mit.edu/course", "Documentation", "x" * 100), 0)

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
        by_title = {source["file_name"]: source for source in sources}
        self.assertIn("Python 3.14", by_title)
        self.assertIn("Released in October", by_title["Python 3.14"]["quote"])


if __name__ == "__main__":
    unittest.main()
