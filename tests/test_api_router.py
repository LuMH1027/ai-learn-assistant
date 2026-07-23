from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from local_course_agent.api.router import (
    CourseRouteMatch,
    dispatch_course_action,
    match_get_course_action,
    match_post_course_action,
    parse_course_route,
)
from local_course_agent.api.course.errors import ApiError
from local_course_agent.api.server.routes import ServerRoutesMixin
from local_course_agent.store import AppStore


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
        self.assertEqual(
            parse_course_route("/api/courses/os-1/notes/7/delete"),
            ("os-1", "notes/7/delete"),
        )
        self.assertIsNone(parse_course_route("/api/config"))
        self.assertIsNone(parse_course_route("/api/courses/os-1"))

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

    def test_post_note_and_memory_management_routes_match(self):
        update = match_post_course_action("/api/courses/os-1/notes/7")
        delete = match_post_course_action("/api/courses/os-1/notes/7/delete")
        clear = match_post_course_action("/api/courses/os-1/memory/clear")

        self.assertIsNotNone(update)
        self.assertEqual(update.endpoint, "note")
        self.assertEqual(update.params, {"note_id": "7"})
        self.assertIsNotNone(delete)
        self.assertEqual(delete.endpoint, "delete_note")
        self.assertEqual(delete.params, {"note_id": "7"})
        self.assertIsNotNone(clear)
        self.assertEqual(clear.endpoint, "clear_memory")

    def test_unknown_deep_course_routes_do_not_match_dynamic_params(self):
        self.assertIsNone(match_post_course_action("/api/courses/os-1/plan/item-1/extra"))
        self.assertIsNone(match_get_course_action("/api/courses/os-1/plan"))
        self.assertIsNone(match_post_course_action("/api/courses/os-1/plan"))
        self.assertIsNone(match_post_course_action("/api/courses/os-1/plan/item-42"))
        self.assertIsNone(match_post_course_action("/api/courses/os-1/plan/42/delete"))
        self.assertIsNone(match_post_course_action("/api/courses/os-1/notes/7/archive"))

    def test_post_mastery_mistake_resolve_route_extracts_mistake_id(self):
        match = match_post_course_action("/api/courses/os-1/mastery/mistakes/mistake-42/resolve")

        self.assertIsNotNone(match)
        self.assertEqual(match.course_id, "os-1")
        self.assertEqual(match.endpoint, "resolve_mastery_mistake")
        self.assertEqual(match.params, {"mistake_id": "mistake-42"})

    def test_dispatch_course_action_invokes_mapped_handler_with_params(self):
        class Target:
            def update_item(self, course_id, item_id):
                return {"course_id": course_id, "item_id": item_id}

        payload = dispatch_course_action(
            Target(),
            CourseRouteMatch(
                course_id="os-1",
                action="notes/item-42",
                endpoint="note",
                params={"item_id": "item-42"},
            ),
            {"note": "update_item"},
        )

        self.assertEqual(payload, {"course_id": "os-1", "item_id": "item-42"})

    def test_course_note_and_memory_handlers_update_store(self):
        class Target(ServerRoutesMixin):
            def __init__(self, store, body=None):
                self.ctx = SimpleNamespace(store=store)
                self.body = body or {}

            def read_body(self):
                return self.body

            def send_json(self, payload, status=HTTPStatus.OK):
                return {"status": status, "payload": payload}

            def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
                return {"status": status, "payload": {"ok": False, "error": message}}

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.add_note("course-1", "旧标题", "旧内容")
            note_id = str(store.list_notes("course-1")[0]["id"])
            store.add_message("course-1", "user", "解释页表")
            store.update_memory_from_question("course-1", "解释页表")

            update = Target(store, {"content": "新内容"}).update_course_note("course-1", note_id)
            delete = Target(store).delete_course_note("course-1", note_id)
            clear = Target(store).clear_course_memory("course-1")
            missing = Target(store).delete_course_note("course-1", note_id)

            self.assertEqual(update["status"], HTTPStatus.OK)
            self.assertEqual(update["payload"]["note"]["content"], "新内容")
            self.assertEqual(delete["payload"]["notes"], [])
            self.assertEqual(clear["payload"], {"ok": True, "messages": [], "memory": ""})
            self.assertEqual(missing["status"], HTTPStatus.NOT_FOUND)

    def test_mastery_mistake_handler_marks_mistake_resolved(self):
        class Target(ServerRoutesMixin):
            def __init__(self, store):
                self.ctx = SimpleNamespace(
                    find_course=lambda course_id: {"id": course_id, "name": course_id},
                    store=store,
                )

            def send_json(self, payload, status=HTTPStatus.OK):
                return {"status": status, "payload": payload}

            def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
                return {"status": status, "payload": {"ok": False, "error": message}}

            def send_service_json(self, action, status=HTTPStatus.OK):
                try:
                    return self.send_json(action(), status)
                except ApiError as exc:
                    return self.send_error_json(exc.message, exc.status)

        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.upsert_mastery_knowledge_point("course-1", {"id": "kp-page-table", "title": "页表地址转换"})
            state = store.apply_mastery_answer_result(
                "course-1",
                "kp-page-table",
                correct=False,
                question="解释页表地址转换。",
            )
            mistake_id = state["mistakes"][0]["id"]

            resolved = Target(store).resolve_mastery_mistake("course-1", mistake_id)
            missing = Target(store).resolve_mastery_mistake("course-1", "missing")

            self.assertEqual(resolved["status"], HTTPStatus.OK)
            self.assertTrue(resolved["payload"]["ok"])
            self.assertEqual(resolved["payload"]["mastery"]["mistakes"][0]["status"], "resolved")
            self.assertEqual(missing["status"], HTTPStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
