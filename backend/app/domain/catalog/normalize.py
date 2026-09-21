from __future__ import annotations

import re
import unicodedata


def normalize_product_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", stripped.strip().lower())
    return collapsed
