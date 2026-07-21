"""Compatibility alias for ``local_course_agent.retrieval.vector_index``."""

import sys

from local_course_agent.retrieval import vector_index as _impl

sys.modules[__name__] = _impl
