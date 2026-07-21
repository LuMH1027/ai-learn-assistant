import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_course_agent.rag import CourseKnowledgeBase, tokenize


class CourseKnowledgeBaseTest(unittest.TestCase):
    def test_chinese_tokenization_keeps_terms_and_character_ngrams(self):
        tokens = tokenize("虚拟内存 page table")

        self.assertIn("虚拟内存", tokens)
        self.assertIn("虚拟", tokens)
        self.assertIn("内存", tokens)
        self.assertIn("page", tokens)

    def test_query_is_limited_to_current_course_and_returns_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            kb = CourseKnowledgeBase(storage)
            kb.index_text(
                course_id="os",
                file_id="os-file",
                file_name="process.md",
                text="进程是资源分配和调度的基本单位。页表用于虚拟内存地址映射。",
            )
            kb.index_text(
                course_id="math",
                file_id="math-file",
                file_name="calculus.md",
                text="导数描述函数变化率，积分描述累积量。",
            )

            result = kb.answer("os", "什么是页表？")

            self.assertIn("页表", result["answer"])
            self.assertEqual(result["citations"][0]["file_name"], "process.md")
            self.assertNotIn("calculus.md", result["answer"])
            self.assertEqual(result["retrieval_quality"], "sufficient")

    def test_unknown_question_reports_no_reliable_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "f1", "intro.md", "操作系统负责管理计算机资源。")

            result = kb.answer("os", "量子纠缠是什么？")

            self.assertIn("未在当前课程资料中找到可靠依据", result["answer"])
            self.assertEqual(result["citations"], [])
            self.assertEqual(result["retrieval_quality"], "none")

    def test_question_words_alone_do_not_create_false_course_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "f1", "intro.md", "操作系统是什么，以及它有哪些主要作用？")

            result = kb.answer("os", "量子纠缠是什么，有哪些作用？")

            self.assertEqual(result["mode"], "no_basis")
            self.assertEqual(result["citations"], [])

    def test_short_numeric_version_parts_do_not_match_list_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "quiz", "复习题.txt", "1. 解释进程。2. 解释线程。3. 解释页表。")

            result = kb.answer("os", "Python 3.14 在什么时候正式发布？")

            self.assertEqual(result["retrieval_quality"], "none")
            self.assertEqual(result["citations"], [])

    def test_legacy_generated_artifacts_are_filtered_from_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "generated", "课程摘要-20260716-154735.md", "页表用于地址转换。")
            kb.index_text("os", "source", "教材.md", "页表项保存虚拟页到物理页框的映射。")

            hits = kb.search("os", "页表地址转换", limit=4)

            self.assertEqual([hit["file_name"] for hit in hits], ["教材.md"])

    def test_bm25_does_not_overreward_repeated_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "spam", "重复.md", "页表 " * 80 + "只重复术语。")
            kb.index_text("os", "useful", "教材.md", "页表保存虚拟页到物理页框的映射，用于完成地址转换。")

            hits = kb.search("os", "页表如何完成地址转换？", limit=2)

            self.assertEqual(hits[0]["file_name"], "教材.md")
            self.assertEqual(hits[0]["retrieval_method"], "bm25_rrf_mmr")

    def test_search_diversifies_sources_and_expands_neighbor_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            long_text = (
                "虚拟内存先把进程地址空间划分为页面。" * 18
                + "页表项记录虚拟页号到物理页框号的映射，并包含有效位。"
                + "发生缺页时操作系统调页并更新页表。" * 18
            )
            kb.index_text("os", "book", "教材.md", long_text)
            kb.index_text("os", "slides", "课件.md", "地址转换会查询页表，TLB 用来缓存常用页表项。")

            hits = kb.search("os", "页表 地址转换 TLB", limit=3)

            self.assertGreaterEqual(len({hit["file_id"] for hit in hits}), 2)
            book_hit = next(hit for hit in hits if hit["file_id"] == "book")
            self.assertGreater(len(book_hit["context_text"]), len(book_hit["text"]))

    def test_markdown_headings_become_retrievable_chunk_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text(
                "os",
                "memory",
                "内存.md",
                "# 虚拟内存\n页表保存虚拟页到物理页框的映射。\n\n# 文件系统\n目录项记录文件名和 inode。",
            )

            hits = kb.search("os", "虚拟内存 页表", limit=1)
            answer = kb.answer("os", "虚拟内存中的页表是什么？")

            self.assertEqual(hits[0]["section_title"], "虚拟内存")
            self.assertEqual(hits[0]["material_type"], "material")
            self.assertEqual(answer["citations"][0]["section_title"], "虚拟内存")
            self.assertIn("retrieval_trace", answer)
            self.assertEqual(answer["retrieval_trace"]["selected"][0]["section_title"], "虚拟内存")

    def test_index_file_records_schema_and_tokenizer_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            kb = CourseKnowledgeBase(storage)
            kb.index_text("os", "book", "教材.md", "页表用于地址转换。")

            payload = json.loads((storage / "os.json").read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["tokenizer_version"], "zh_ngrams_v2")
            self.assertEqual(payload["chunks"][0]["material_type"], "textbook")

    def test_generate_summary_and_quiz_from_course_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("ds", "stack", "栈.md", "栈是后进先出的线性表，常用于函数调用和括号匹配。")
            kb.index_text("ds", "queue", "队列.md", "队列是先进先出的线性表，常用于任务调度和广度优先搜索。")

            summary = kb.generate_summary("ds")
            quiz = kb.generate_quiz("ds", count=2)

            self.assertIn("课程复习摘要", summary["content"])
            self.assertIn("## 核心知识点", summary["content"])
            self.assertIn("复习建议", summary["content"])
            self.assertGreaterEqual(len(summary["citations"]), 2)
            self.assertIn("自测题", quiz["content"])
            self.assertIn("应用题", quiz["content"])
            self.assertEqual(len(quiz["citations"]), 2)

    def test_summary_selects_representative_chunks_across_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "intro", "导论.md", "操作系统管理资源。" * 60)
            kb.index_text("os", "memory", "内存.md", "页表保存虚拟页到物理页框的映射，用于地址转换。")
            kb.index_text("os", "process", "进程.md", "进程调度决定 CPU 在多个进程之间的分配。")

            summary = kb.generate_summary("os", limit=2)
            citation_files = {citation["file_name"] for citation in summary["citations"]}

            self.assertEqual(len(citation_files), 2)
            self.assertNotEqual(citation_files, {"导论.md"})

    def test_rebuild_course_writes_all_documents_at_once_and_replaces_old_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "old", "旧资料.md", "旧索引内容。")

            total = kb.rebuild_course(
                "os",
                [
                    {
                        "file_id": "book",
                        "file_name": "教材.md",
                        "pages": [
                            {"page": 1, "text": "页表用于虚拟地址到物理地址转换。"},
                            {"page": 2, "text": "TLB 缓存常用页表项。"},
                        ],
                    },
                    {
                        "file_id": "slides",
                        "file_name": "课件.md",
                        "pages": [{"page": None, "text": "缺页中断会触发调页。"}],
                    },
                ],
            )

            hits = kb.search("os", "页表 TLB 缺页", limit=5)

            self.assertEqual(total, 3)
            self.assertEqual({hit["file_name"] for hit in hits}, {"教材.md", "课件.md"})
            self.assertNotIn("旧资料.md", [hit["file_name"] for hit in hits])

    def test_hybrid_search_expands_related_course_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "TLB 缓存常用页表项，可以加速虚拟地址到物理地址的访问。")

            lexical_hits = kb.search("os", "后备缓冲为什么更快？", strategy="lexical")
            hybrid_hits = kb.search("os", "后备缓冲为什么更快？", strategy="hybrid")

            self.assertEqual(lexical_hits, [])
            self.assertEqual(hybrid_hits[0]["file_name"], "教材.md")
            self.assertEqual(hybrid_hits[0]["retrieval_method"], "hybrid_bm25_semantic_rrf_mmr")

    def test_hybrid_search_uses_local_semantic_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("ds", "stack", "栈.md", "栈保存函数调用现场，遵循 LIFO 访问顺序。")

            hits = kb.search("ds", "递归调用为什么要用后进先出结构？", strategy="hybrid")

            self.assertEqual(hits[0]["file_name"], "栈.md")
            self.assertIn(
                hits[0]["retrieval_method"],
                {"hybrid_bm25_semantic_rrf_mmr", "hybrid_lexical_vector_rrf"},
            )

    def test_hybrid_search_merges_vector_hits_into_main_rag_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "lexical", "页表.md", "页表保存虚拟页到物理页框的映射。")
            kb.index_text("os", "vector", "TLB.md", "TLB 缓存热项，降低访存延迟。")

            class FakeVectorIndex:
                def search(self, query, limit=5, min_score=None):
                    self.query = query
                    self.limit = limit
                    self.min_score = min_score
                    return [
                        {
                            "id": "vector-text-2",
                            "file_id": "vector",
                            "file_name": "TLB.md",
                            "page": None,
                            "chunk_index": 2,
                            "text": "TLB 缓存热项，降低访存延迟。",
                            "vector_score": 0.91,
                        }
                    ]

            fake_vector_index = FakeVectorIndex()
            with mock.patch(
                "local_course_agent.rag.build_vector_index_from_chunks",
                return_value=fake_vector_index,
            ) as build_vector_index:
                hits = kb.search("os", "页表如何映射地址？", limit=2, strategy="hybrid")

            build_vector_index.assert_called_once()
            self.assertEqual(fake_vector_index.query, "页表 映射地址？")
            self.assertEqual(fake_vector_index.min_score, 0.2)
            self.assertIn("TLB.md", [hit["file_name"] for hit in hits])
            vector_hit = next(hit for hit in hits if hit["file_name"] == "TLB.md")
            self.assertIn("vector", vector_hit["retrieval_sources"])
            self.assertIn(
                vector_hit["retrieval_method"],
                {"vector", "hybrid_lexical_vector_rrf"},
            )
            self.assertEqual(vector_hit["vector_score"], 0.91)

    def test_hybrid_search_falls_back_to_lexical_when_vector_index_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "页表保存虚拟页到物理页框的映射。")

            with mock.patch(
                "local_course_agent.rag.build_vector_index_from_chunks",
                side_effect=RuntimeError("embedding unavailable"),
            ):
                hits = kb.search("os", "页表映射", limit=1, strategy="hybrid")

            self.assertEqual(hits[0]["file_name"], "教材.md")
            self.assertEqual(hits[0]["retrieval_method"], "hybrid_bm25_semantic_rrf_mmr")


if __name__ == "__main__":
    unittest.main()
