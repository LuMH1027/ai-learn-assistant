import unittest

from local_course_agent.citation_check import (
    check_citations,
    postprocess_answer_with_citation_check,
    split_sentences,
    token_overlap,
)


class CitationCheckTest(unittest.TestCase):
    def test_split_sentences_keeps_citation_labels(self):
        sentences = split_sentences("# 摘要\n- 页表用于地址转换。[L1]\n复习时先看例题。")

        self.assertEqual(sentences, ["页表用于地址转换。[L1]", "复习时先看例题。"])

    def test_flags_assertive_sentence_without_citation(self):
        result = check_citations(
            "页表保存虚拟页到物理页框的映射。",
            [{"source_type": "local", "quote": "页表保存虚拟页到物理页框的映射。"}],
        )

        self.assertFalse(result["supported"])
        self.assertEqual(result["stats"]["uncited_count"], 1)
        self.assertEqual(result["unsupported_claims"][0]["reason"], "missing_citation")

    def test_accepts_claim_with_enough_quote_overlap(self):
        result = check_citations(
            "页表保存虚拟页到物理页框的映射，用于地址转换。[L1]",
            [{"source_type": "local", "quote": "页表保存虚拟页到物理页框的映射，TLB 可加速地址转换。"}],
        )

        self.assertTrue(result["supported"])
        self.assertGreaterEqual(result["claims"][0]["max_overlap"], 0.18)

    def test_reports_low_overlap_for_unsupported_cited_claim(self):
        result = check_citations(
            "时间片轮转调度一定能避免所有饥饿问题。[L1]",
            [{"source_type": "local", "quote": "页表保存虚拟页到物理页框的映射，用于地址转换。"}],
        )

        self.assertFalse(result["supported"])
        self.assertEqual(result["unsupported_claims"][0]["reason"], "low_overlap")

    def test_maps_web_and_plain_citation_labels(self):
        result = check_citations(
            "网页资料说明 Python 3.13 发布于 2024 年。[W1] 课程资料说明页表用于地址转换。[2]",
            [
                {"source_type": "web", "quote": "Python 3.13 发布于 2024 年。"},
                {"source_type": "local", "quote": "页表用于地址转换。"},
            ],
        )

        self.assertTrue(result["supported"])
        self.assertIn("W1", result["citation_labels"])
        self.assertIn("2", result["citation_labels"])

    def test_ignores_questions_and_advice_sentences(self):
        result = check_citations(
            "页表是什么？建议先复述定义，再回到原文核对例题。",
            [],
        )

        self.assertTrue(result["supported"])
        self.assertEqual(result["stats"]["assertive_claim_count"], 0)

    def test_token_overlap_counts_chinese_and_english_terms(self):
        score = token_overlap("TLB 加速 virtual memory 地址转换", "TLB 用于加速 virtual memory 的地址转换过程")

        self.assertGreater(score, 0.5)

    def test_postprocess_normal_mode_keeps_answer_and_returns_check(self):
        answer = "页表保存虚拟页到物理页框的映射。"
        payload = postprocess_answer_with_citation_check(
            answer,
            [{"source_type": "local", "quote": "页表保存虚拟页到物理页框的映射。"}],
        )

        self.assertEqual(payload["answer"], answer)
        self.assertFalse(payload["citation_check"]["supported"])
        self.assertEqual(payload["unsupported_claims"][0]["reason"], "missing_citation")

    def test_postprocess_strict_mode_marks_unsupported_claims_without_deleting_content(self):
        answer = "- 页表保存虚拟页到物理页框的映射。\n- 建议先复述定义。"
        payload = postprocess_answer_with_citation_check(answer, [], strict=True)

        self.assertIn("页表保存虚拟页到物理页框的映射。", payload["answer"])
        self.assertIn("页表保存虚拟页到物理页框的映射。（未找到引用支撑）", payload["answer"])
        self.assertIn("- 建议先复述定义。", payload["answer"])
        self.assertEqual(payload["citation_check"]["stats"]["unsupported_count"], 1)


if __name__ == "__main__":
    unittest.main()
