"""Compatibility alias for ``local_course_agent.learning.summary``."""

import sys

from local_course_agent.learning import summary as _impl

sys.modules[__name__] = _impl
