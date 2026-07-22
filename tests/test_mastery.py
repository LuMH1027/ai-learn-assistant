import unittest

from local_course_agent.learning.mastery import (
    apply_answer_result,
    create_knowledge_point,
    create_mastery_state,
    resolve_mistake,
    review_suggestion,
    upsert_knowledge_point,
)
from local_course_agent.learning.mastery.policy import score_delta
from local_course_agent.learning.mastery.schema import normalize_state


class MasteryModelTest(unittest.TestCase):
    def test_upsert_knowledge_point_creates_mastery_record(self):
        state = create_mastery_state(timestamp="2026-07-21 10:00:00")
        point = create_knowledge_point(
            "页表地址转换",
            point_id="kp-address",
            aliases=["虚拟地址转换"],
            source_refs=[{"file_name": "操作系统.md", "page": 3}],
            timestamp="2026-07-21 10:00:00",
        )

        next_state = upsert_knowledge_point(state, point, timestamp="2026-07-21 10:00:00")

        self.assertEqual(next_state["schema_version"], 1)
        self.assertEqual(next_state["knowledge_points"][0]["id"], "kp-address")
        self.assertEqual(next_state["mastery"]["kp-address"]["score"], 50)
        self.assertEqual(next_state["mastery"]["kp-address"]["level"], "building")

    def test_correct_answer_raises_score_and_extends_review_interval(self):
        state = upsert_knowledge_point(
            create_mastery_state(timestamp="2026-07-21 10:00:00"),
            create_knowledge_point("二叉树遍历", point_id="kp-tree", timestamp="2026-07-21 10:00:00"),
            timestamp="2026-07-21 10:00:00",
        )

        next_state = apply_answer_result(
            state,
            "kp-tree",
            correct=True,
            difficulty="hard",
            confidence=0.8,
            timestamp="2026-07-21 10:00:00",
        )

        mastery = next_state["mastery"]["kp-tree"]
        self.assertGreater(mastery["score"], 50)
        self.assertEqual(mastery["attempts"], 1)
        self.assertEqual(mastery["correct_count"], 1)
        self.assertEqual(mastery["wrong_count"], 0)
        self.assertEqual(mastery["last_result"], "correct")
        self.assertIn(mastery["review_interval_days"], {2, 4, 7})
        self.assertFalse(next_state["mistakes"])

    def test_wrong_answer_lowers_score_and_records_mistake(self):
        state = upsert_knowledge_point(
            create_mastery_state(timestamp="2026-07-21 10:00:00"),
            create_knowledge_point("进程调度", point_id="kp-schedule", timestamp="2026-07-21 10:00:00"),
            timestamp="2026-07-21 10:00:00",
        )

        next_state = apply_answer_result(
            state,
            "kp-schedule",
            correct=False,
            question="解释时间片轮转调度。",
            user_answer="按优先级运行。",
            expected_answer="按固定时间片轮流分配 CPU。",
            difficulty="normal",
            source_ref={"file_name": "调度.md", "section_title": "时间片轮转"},
            timestamp="2026-07-21 10:00:00",
        )

        mastery = next_state["mastery"]["kp-schedule"]
        self.assertLess(mastery["score"], 50)
        self.assertEqual(mastery["wrong_count"], 1)
        self.assertEqual(mastery["streak"], 0)
        self.assertEqual(mastery["review_interval_days"], 1)
        self.assertEqual(len(next_state["mistakes"]), 1)
        self.assertEqual(next_state["mistakes"][0]["status"], "open")
        self.assertEqual(next_state["mistakes"][0]["point_id"], "kp-schedule")
        self.assertEqual(next_state["mistakes"][0]["source_ref"]["section_title"], "时间片轮转")

    def test_review_suggestion_depends_on_score(self):
        weak = review_suggestion(35, correct=True, timestamp="2026-07-21 10:00:00")
        familiar = review_suggestion(72, correct=True, timestamp="2026-07-21 10:00:00")
        mastered = review_suggestion(91, correct=True, timestamp="2026-07-21 10:00:00")

        self.assertEqual(weak["interval_days"], 1)
        self.assertEqual(familiar["interval_days"], 4)
        self.assertEqual(mastered["interval_days"], 7)
        self.assertEqual(mastered["next_review_at"], "2026-07-28 10:00:00")

    def test_schema_module_normalizes_legacy_state_shape(self):
        normalized = normalize_state(
            {
                "knowledge_points": [{"title": "  页表   地址转换  ", "aliases": [" 页表 ", "页表"]}],
                "mastery": {"kp-old": {"score": "bad", "attempts": -1, "wrong_count": "2"}},
                "mistakes": [{"point_id": "kp-old", "question": "", "status": "unknown"}],
            },
            timestamp="2026-07-21 10:00:00",
        )

        self.assertEqual(normalized["knowledge_points"][0]["title"], "页表 地址转换")
        self.assertEqual(normalized["knowledge_points"][0]["aliases"], ["页表"])
        self.assertEqual(normalized["mastery"]["kp-old"]["score"], 50)
        self.assertEqual(normalized["mastery"]["kp-old"]["attempts"], 0)
        self.assertEqual(normalized["mastery"]["kp-old"]["wrong_count"], 2)
        self.assertEqual(normalized["mistakes"][0]["status"], "open")
        self.assertEqual(normalized["mistakes"][0]["question"], "未记录题目")

    def test_policy_module_keeps_score_strategy_separate(self):
        easy_delta = score_delta(correct=True, difficulty="easy", current_score=50, streak=0)
        hard_delta = score_delta(correct=True, difficulty="hard", current_score=50, streak=0)
        wrong_delta = score_delta(correct=False, difficulty="normal", current_score=80, streak=3)

        self.assertGreater(hard_delta, easy_delta)
        self.assertLess(wrong_delta, 0)

    def test_resolve_mistake_marks_item_done_without_mutating_input(self):
        state = apply_answer_result(
            upsert_knowledge_point(
                create_mastery_state(timestamp="2026-07-21 10:00:00"),
                create_knowledge_point("栈", point_id="kp-stack", timestamp="2026-07-21 10:00:00"),
                timestamp="2026-07-21 10:00:00",
            ),
            "kp-stack",
            correct=False,
            question="栈的访问顺序是什么？",
            timestamp="2026-07-21 10:00:00",
        )
        mistake = state["mistakes"][0]

        resolved = resolve_mistake(mistake, timestamp="2026-07-22 10:00:00")

        self.assertEqual(mistake["status"], "open")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["point_id"], "kp-stack")
        self.assertEqual(resolved["question"], "栈的访问顺序是什么？")
        self.assertEqual(resolved["review_count"], 1)
        self.assertEqual(resolved["resolved_at"], "2026-07-22 10:00:00")


if __name__ == "__main__":
    unittest.main()
