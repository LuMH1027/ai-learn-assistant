import unittest

from local_course_agent.api.router import (
    CourseRouteMatch,
    dispatch_course_action,
    match_get_course_action,
    match_post_course_action,
    parse_course_route,
)


class ApiRouterTest(unittest.TestCase):
    def test_parse_course_route_decodes_course_and_ignores_query(self):
        self.assertEqual(
            parse_course_route("/api/courses/os%201/messages?cursor=next"),
            ("os 1", "messages"),
        )
        self.assertEqual(
            parse_course_route("/api/courses/os-1/index/jobs"),
            ("os-1", "index/jobs"),
        )
        self.assertIsNone(parse_course_route("/api/config"))
        self.assertIsNone(parse_course_route("/api/courses/os-1/plan/item-1/extra"))

    def test_get_course_actions_match_only_read_routes(self):
        match = match_get_course_action("/api/courses/os-1/dashboard")

        self.assertIsNotNone(match)
        self.assertEqual(match.course_id, "os-1")
        self.assertEqual(match.action, "dashboard")
        self.assertEqual(match.endpoint, "dashboard")
        self.assertEqual(match.params, {})
        self.assertIsNone(match_get_course_action("/api/courses/os-1/chat"))

    def test_post_course_actions_match_write_routes(self):
        chat = match_post_course_action("/api/courses/os-1/chat")
        index_job = match_post_course_action("/api/courses/os-1/index/jobs")

        self.assertIsNotNone(chat)
        self.assertEqual(chat.endpoint, "chat")
        self.assertIsNotNone(index_job)
        self.assertEqual(index_job.endpoint, "index_jobs")
        self.assertIsNone(match_post_course_action("/api/courses/os-1/messages"))

    def test_post_plan_item_route_extracts_item_id(self):
        match = match_post_course_action("/api/courses/os-1/plan/item-42")

        self.assertIsNotNone(match)
        self.assertEqual(match.course_id, "os-1")
        self.assertEqual(match.action, "plan/item-42")
        self.assertEqual(match.endpoint, "plan_item")
        self.assertEqual(match.params, {"item_id": "item-42"})

    def test_dispatch_course_action_invokes_mapped_handler_with_params(self):
        class Target:
            def update_item(self, course_id, item_id):
                return {"course_id": course_id, "item_id": item_id}

        payload = dispatch_course_action(
            Target(),
            CourseRouteMatch(
                course_id="os-1",
                action="plan/item-42",
                endpoint="plan_item",
                params={"item_id": "item-42"},
            ),
            {"plan_item": "update_item"},
        )

        self.assertEqual(payload, {"course_id": "os-1", "item_id": "item-42"})


if __name__ == "__main__":
    unittest.main()
