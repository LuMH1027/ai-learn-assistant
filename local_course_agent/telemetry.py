"""Compatibility alias for ``local_course_agent.ops.telemetry``."""

import sys

from local_course_agent.ops import telemetry as _impl

sys.modules[__name__] = _impl
