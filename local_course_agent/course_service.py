"""Compatibility alias for ``local_course_agent.learning.service``."""

import sys

from local_course_agent.learning import service as _impl

sys.modules[__name__] = _impl
