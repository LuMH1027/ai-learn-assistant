"""Compatibility alias for ``local_course_agent.retrieval.rag_eval``."""

import sys

from local_course_agent.retrieval import rag_eval as _impl

sys.modules[__name__] = _impl
