"""Compatibility alias for ``local_course_agent.ingestion.parser_quality``."""

import sys

from local_course_agent.ingestion import parser_quality as _impl

sys.modules[__name__] = _impl
