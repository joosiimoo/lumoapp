"""Per-business transaction sequence formatting (Número de transacción)."""

from __future__ import annotations

_TRX_PREFIX = "TRX"
_PAD_WIDTH = 6


def format_transaction_number(sequence: int) -> str:
    """Format a numeric sequence as TRX-000001 (wider after 999999)."""
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("transaction sequence must be a positive int")
    width = _PAD_WIDTH if sequence <= 10**_PAD_WIDTH - 1 else len(str(sequence))
    return f"{_TRX_PREFIX}-{sequence:0{width}d}"
