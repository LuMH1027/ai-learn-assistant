import unittest

from local_course_agent.conversation_context import (
    build_contextual_retrieval_query,
    compress_recent_turns,
    detect_follow_up_signals,
    extract_referenced_text,
    recent_conversation_turns,
)


class ConversationContextTest(unittest.TestCase):
    def test_detects_demonstrative_follow_up_terms(self):
        signals = detect_follow_up_signals("这个为什么会导致缺页？")

        self.assertIn("这个", signals)

    def test_independent_question_is_not_rewritten(self):
        result = build_contextual_retrieval_query(
            "解释页表在地址转换中的作用",
            [
                {"role": "user", "content": "什么是进程？"},
                {"role": "assistant", "content": "进程是资源分配单位。"},
            ],
        )

        self.assertFalse(result.is_follow_up)
        self.assertEqual(result.retrieval_query, "解释页表在地址转换中的作用")
        self.assertEqual(result.context_turns_used, 0)

    def test_short_standalone_term_is_not_a_follow_up_by_question_mark_only(self):
        signals = detect_follow_up_signals("页表？")

        self.assertEqual(signals, ())

    def test_rewrites_this_question_with_recent_context(self):
        result = build_contextual_retrieval_query(
            "这个为什么更快？",
            [
                {"role": "user", "content": "TLB 在页表地址转换中起什么作用？"},
                {"role": "assistant", "content": "TLB 缓存常用页表项，减少访问页表次数。"},
            ],
        )

        self.assertTrue(result.is_follow_up)
        self.assertIn("TLB", result.retrieval_query)
        self.assertIn("页表地址转换", result.retrieval_query)
        self.assertIn("这个为什么更快", result.retrieval_query)

    def test_rewrites_above_reference_with_latest_turns_only(self):
        result = build_contextual_retrieval_query(
            "上面那个算法复杂度呢？",
            [
                {"role": "user", "content": "很早的问题，不应该被保留。"},
                {"role": "assistant", "content": "很早的回答。"},
                {"role": "user", "content": "归并排序为什么稳定？"},
                {"role": "assistant", "content": "合并时相等元素保持原顺序。"},
                {"role": "user", "content": "快速排序的划分过程是什么？"},
                {"role": "assistant", "content": "选择 pivot 后把数组划分为左右两部分。"},
            ],
            max_turns=2,
        )

        self.assertTrue(result.is_follow_up)
        self.assertIn("快速排序", result.retrieval_query)
        self.assertIn("归并排序", result.retrieval_query)
        self.assertNotIn("很早的问题", result.retrieval_query)

    def test_extracts_numbered_question_reference(self):
        turns = recent_conversation_turns(
            [
                {"role": "user", "content": "1. 解释页表。2. TLB 为什么能加速地址转换？3. 缺页中断流程。"},
                {"role": "assistant", "content": "先看每个小问涉及的概念。"},
            ]
        )

        referenced = extract_referenced_text("第二问怎么做？", turns)
        result = build_contextual_retrieval_query("第二问怎么做？", [
            {"role": "user", "content": "1. 解释页表。2. TLB 为什么能加速地址转换？3. 缺页中断流程。"},
            {"role": "assistant", "content": "先看每个小问涉及的概念。"},
        ])

        self.assertIn("TLB 为什么能加速地址转换", referenced)
        self.assertTrue(result.is_follow_up)
        self.assertIn("TLB 为什么能加速地址转换", result.retrieval_query)
        self.assertNotIn("缺页中断流程", result.retrieval_query)

    def test_short_follow_up_uses_context(self):
        result = build_contextual_retrieval_query(
            "怎么做？",
            [{"role": "user", "content": "用栈判断括号匹配的步骤是什么？"}],
        )

        self.assertTrue(result.is_follow_up)
        self.assertIn("栈判断括号匹配", result.retrieval_query)

    def test_compressed_context_is_bounded(self):
        turns = tuple(f"用户：第 {index} 轮 " + "虚拟内存" * 60 for index in range(4))

        compact = compress_recent_turns(turns, max_chars=120)

        self.assertLessEqual(len(compact), 120)

    def test_zero_recent_turns_returns_empty_context(self):
        turns = recent_conversation_turns(
            [{"role": "user", "content": "什么是页表？"}],
            max_turns=0,
        )

        self.assertEqual(turns, ())


if __name__ == "__main__":
    unittest.main()
