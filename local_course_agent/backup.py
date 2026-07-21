"""Compatibility alias for ``local_course_agent.ops.backup``."""

import sys

from local_course_agent.ops import backup as _impl

sys.modules[__name__] = _impl
