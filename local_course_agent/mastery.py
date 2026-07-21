"""Compatibility alias for ``local_course_agent.learning.mastery``."""

import sys

from local_course_agent.learning import mastery as _impl

sys.modules[__name__] = _impl
