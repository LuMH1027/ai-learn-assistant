from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class CourseActionRoute:
    action: str
    endpoint: str
    param_name: str | None = None
    suffix: str | None = None

    def match(self, action: str) -> dict[str, str] | None:
        if self.param_name is None:
            return {} if action == self.action else None
        prefix = f"{self.action}/"
        if not action.startswith(prefix):
            return None
        value = action[len(prefix):]
        if self.suffix is not None:
            suffix = f"/{self.suffix}"
            if not value.endswith(suffix):
                return None
            value = value[: -len(suffix)]
        if not value or "/" in value:
            return None
        return {self.param_name: unquote(value)}


@dataclass(frozen=True)
class CourseRouteMatch:
    course_id: str
    action: str
    endpoint: str
    params: dict[str, str] = field(default_factory=dict)


GET_COURSE_ACTIONS = (
    CourseActionRoute("messages", "messages"),
    CourseActionRoute("memory", "memory"),
    CourseActionRoute("summary", "summary"),
    CourseActionRoute("quiz", "quiz"),
    CourseActionRoute("notes", "notes"),
    CourseActionRoute("plan", "plan"),
    CourseActionRoute("dashboard", "dashboard"),
    CourseActionRoute("mastery", "mastery"),
)

POST_COURSE_ACTIONS = (
    CourseActionRoute("index", "index"),
    CourseActionRoute("index/jobs", "index_jobs"),
    CourseActionRoute("files", "files"),
    CourseActionRoute("chat", "chat"),
    CourseActionRoute("summary", "summary"),
    CourseActionRoute("quiz", "quiz"),
    CourseActionRoute("notes", "notes"),
    CourseActionRoute("notes", "delete_note", "note_id", suffix="delete"),
    CourseActionRoute("notes", "note", "note_id"),
    CourseActionRoute("memory/clear", "clear_memory"),
    CourseActionRoute("plan", "plan"),
    CourseActionRoute("plan", "plan_item", "item_id"),
    CourseActionRoute("mastery", "mastery"),
)


def parse_course_route(request_path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"/api/courses/([^/]+)/(.+)", urlparse(request_path).path)
    if not match:
        return None
    course_id = unquote(match.group(1))
    action = match.group(2)
    return course_id, action


def match_course_action(
    request_path: str,
    routes: tuple[CourseActionRoute, ...],
) -> CourseRouteMatch | None:
    parsed = parse_course_route(request_path)
    if not parsed:
        return None
    course_id, action = parsed
    for route in routes:
        params = route.match(action)
        if params is not None:
            return CourseRouteMatch(
                course_id=course_id,
                action=action,
                endpoint=route.endpoint,
                params=params,
            )
    return None


def match_get_course_action(request_path: str) -> CourseRouteMatch | None:
    return match_course_action(request_path, GET_COURSE_ACTIONS)


def match_post_course_action(request_path: str) -> CourseRouteMatch | None:
    return match_course_action(request_path, POST_COURSE_ACTIONS)


def dispatch_course_action(
    target: object,
    route: CourseRouteMatch,
    handler_names: Mapping[str, str],
):
    handler_name = handler_names[route.endpoint]
    handler = getattr(target, handler_name)
    return handler(route.course_id, **route.params)
