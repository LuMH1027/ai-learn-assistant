"""Compatibility alias for ``local_course_agent.ops.config_status``."""

import sys

from local_course_agent.ops import config_status as _impl

sys.modules[__name__] = _impl
