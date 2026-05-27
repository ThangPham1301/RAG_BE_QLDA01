from __future__ import annotations

from typing import Any, Dict


def is_valid_signer_field(signer: Dict[str, Any] | None) -> bool:
    if not signer:
        return False
    if signer.get("status") != "found":
        return False
    if not signer.get("value"):
        return False
    if float(signer.get("confidence") or 0) < 0.55:
        return False
    evidence = signer.get("evidence") or []
    return bool(evidence)


def is_valid_extracted_field(field: Dict[str, Any] | None) -> bool:
    if not field:
        return False
    if field.get("status") != "found":
        return False
    if not field.get("value"):
        return False
    return float(field.get("confidence") or 0) >= 0.5
