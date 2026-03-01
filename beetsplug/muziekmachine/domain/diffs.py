from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple


ChangeMap = Dict[str, Tuple[Any, Any]]


@dataclass(frozen=True)
class Diff:
    """Song-level field diff between source-current and desired-canonical projections.

    `changes` stores `{field: (old_value, new_value)}`.
    """

    changes: ChangeMap = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.changes

    def filter(self, allowed_fields: Iterable[str]) -> "Diff":
        allowed = set(allowed_fields)
        return Diff({k: v for k, v in self.changes.items() if k in allowed})


def normalize_value(value: Any) -> Any:
    """Normalize values for song diff comparisons.

    Phase 0 convention: treat `None` and empty-string as equivalent.
    """

    if value is None or value == "":
        return None
    return value


def compute(
    current: Dict[str, Any],
    desired: Dict[str, Any],
    *,
    equivalence_overrides: Optional[Dict[str, tuple[Any, ...]]] = None,
) -> Diff:
    """Compute field-level diff between source-projected current and desired song state.

    Parameters
    ----------
    current
        Current source projection (e.g., from `SourceAdapter.render_current`).
    desired
        Desired source projection (e.g., from `SourceAdapter.render_desired`).
    equivalence_overrides
        Optional map `{field: equivalent_values}` for field-specific normalization.

    Returns
    -------
    Diff
        Deterministic map of changed fields.
    """

    changes: ChangeMap = {}
    overrides = equivalence_overrides or {}

    for field in sorted(set(current) | set(desired)):
        old_raw = current.get(field)
        new_raw = desired.get(field)

        old_norm = normalize_value(old_raw)
        new_norm = normalize_value(new_raw)

        if field in overrides:
            eq_values = set(overrides[field])
            if old_norm in eq_values:
                old_norm = None
            if new_norm in eq_values:
                new_norm = None

        if old_norm != new_norm:
            changes[field] = (old_raw, new_raw)

    return Diff(changes)
