from __future__ import annotations

from local_course_agent.learning.mastery.builders import (
    create_knowledge_point,
    create_mastery_record,
    create_mastery_state,
    create_mistake_record,
)
from local_course_agent.learning.mastery.normalization import (
    SCHEMA_VERSION,
    clean_text,
    merge_refs,
    merge_unique,
    normalize_knowledge_point,
    normalize_mastery_record,
    normalize_mistake_record,
    normalize_ref,
    normalize_refs,
    normalize_state,
    normalize_text_list,
    positive_int,
    stable_id,
)
from local_course_agent.learning.mastery.operations import (
    apply_answer_result,
    resolve_mistake,
    update_mastery_for_answer,
    upsert_knowledge_point,
)
from local_course_agent.learning.mastery.policy import (
    DEFAULT_MASTERY_SCORE,
    DIFFICULTY_WEIGHTS,
    MAX_MASTERY_SCORE,
    MIN_MASTERY_SCORE,
    clamp_float,
    clamp_score,
    format_time,
    mastery_level,
    now_text,
    parse_time,
    review_suggestion,
    score_delta,
)
