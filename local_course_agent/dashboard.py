"""Compatibility alias for ``local_course_agent.learning.dashboard``."""

import sys

from local_course_agent.learning import dashboard as _impl

sys.modules[__name__] = _impl
