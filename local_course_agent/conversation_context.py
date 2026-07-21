"""Compatibility alias for ``local_course_agent.retrieval.conversation_context``."""

import sys

from local_course_agent.retrieval import conversation_context as _impl

sys.modules[__name__] = _impl
