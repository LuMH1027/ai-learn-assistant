from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Optional


def image_to_data_url(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > 5 * 1024 * 1024:
            return None
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError:
        return None
