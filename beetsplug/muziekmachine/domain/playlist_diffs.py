from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class FieldDiff:
    """Field-level metadata changes for a playlist."""

    changes: Dict[str, Tuple[Any, Any]]


@dataclass
class MembershipOp:
    """A single playlist membership operation.

    - op: "add" | "remove" | "move"
    - song_key: stable membership key, e.g. "spotify:<track_id>" or "song:<canonical_id>"
    - index: target index for add/move; source index for remove
    """

    op: str
    song_key: str
    index: int


@dataclass
class MembershipDiff:
    """Ordered operations to transform current membership into desired membership."""

    ops: List[MembershipOp]


def _normalize_field_value(value: Any) -> Any:
    """Normalize values for diff comparisons.

    We intentionally treat None and empty-string as equivalent for textual metadata.
    """

    if value is None or value == "":
        return None
    return value


def compute_field_diff(current: Dict[str, Any], desired: Dict[str, Any]) -> FieldDiff:
    """Compute field-level changes between current and desired playlist metadata."""

    changes: Dict[str, Tuple[Any, Any]] = {}

    for key in sorted(set(current) | set(desired)):
        cur_value = _normalize_field_value(current.get(key))
        des_value = _normalize_field_value(desired.get(key))

        if cur_value != des_value:
            changes[key] = (current.get(key), desired.get(key))

    return FieldDiff(changes)


def _dedupe_preserve_order(keys: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for key in keys:
        if key not in seen:
            out.append(key)
            seen.add(key)
    return out


def compute_membership_diff(current_keys: List[str], desired_keys: List[str]) -> MembershipDiff:
    """Compute a deterministic, readable membership diff.

    Design choices for muziekmachine Phase 0:
    - Duplicates are not supported in target membership. Desired is de-duplicated.
    - Plan correctness/readability is preferred over strict minimality.
    - Operations are generated in a deterministic sequence.
    """

    ops: List[MembershipOp] = []

    desired_unique = _dedupe_preserve_order(desired_keys)
    desired_set = set(desired_unique)

    # Work on a mutable copy so operation decisions are always based on the
    # latest transformed state.
    working: List[str] = list(current_keys)

    # 1) Remove entries that are either not desired or duplicates.
    remove_indices: List[int] = []
    seen_left: set[str] = set()
    for idx, key in enumerate(working):
        is_not_desired = key not in desired_set
        is_duplicate = key in seen_left
        if is_not_desired or is_duplicate:
            remove_indices.append(idx)
        else:
            seen_left.add(key)

    for idx in reversed(remove_indices):
        key = working[idx]
        ops.append(MembershipOp("remove", key, idx))
        working.pop(idx)

    # 2) Reorder existing keys and add missing keys to match desired order.
    for target_idx, key in enumerate(desired_unique):
        if target_idx < len(working) and working[target_idx] == key:
            continue

        if key in working:
            current_idx = working.index(key)
            working.pop(current_idx)
            working.insert(target_idx, key)
            ops.append(MembershipOp("move", key, target_idx))
        else:
            working.insert(target_idx, key)
            ops.append(MembershipOp("add", key, target_idx))

    return MembershipDiff(ops)
