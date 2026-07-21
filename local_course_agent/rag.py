"""Compatibility alias for ``local_course_agent.retrieval.rag``."""

import sys

from local_course_agent.retrieval import rag as _impl

sys.modules[__name__] = _impl
