"""Compatibility alias for ``local_course_agent.retrieval.citation_check``."""

import sys

from local_course_agent.retrieval import citation_check as _impl

sys.modules[__name__] = _impl
