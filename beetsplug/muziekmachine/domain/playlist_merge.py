from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional

from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer

PlaylistMergeMode = Literal["union", "left_to_right", "right_to_left"]


@dataclass(frozen=True)
class PlaylistSyncPlan:
    """Desired membership keys to apply per side after merge planning."""

    left_desired_keys: list[str]
    right_desired_keys: list[str]


def _member_key(pointer: SongPointer) -> Optional[str]:
    if pointer.song_id:
        return f"song:{pointer.song_id}"

    ref: Any = pointer.source_ref
    if not ref:
        return None

    # Backward-compatible with dict-like refs used by older adapters.
    if isinstance(ref, dict):
        source = ref.get("source")
        external_id = ref.get("external_id") or ref.get("id")
        if source and external_id:
            return f"{source}:{external_id}"
        return None

    source = getattr(ref, "source", None)
    external_id = getattr(ref, "external_id", None) or getattr(ref, "id", None)
    if source and external_id:
        return f"{source}:{external_id}"

    return None


def membership_keys(playlist: PlaylistData) -> list[str]:
    """Extract ordered stable membership keys from PlaylistData."""

    keys: list[str] = []
    for pointer in playlist.members or []:
        key = _member_key(pointer)
        if key:
            keys.append(key)
    return keys


def _dedupe_preserve_order(keys: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def merge_membership_keys(
    left: PlaylistData,
    right: PlaylistData,
    *,
    mode: PlaylistMergeMode = "union",
) -> list[str]:
    """Resolve target membership keys for a pair of matched playlists.

    Modes:
    - union: unique(left + right)
    - left_to_right: right should become left
    - right_to_left: left should become right
    """

    left_keys = _dedupe_preserve_order(membership_keys(left))
    right_keys = _dedupe_preserve_order(membership_keys(right))

    if mode == "union":
        return _dedupe_preserve_order([*left_keys, *right_keys])
    if mode == "left_to_right":
        return left_keys
    if mode == "right_to_left":
        return right_keys
    raise ValueError(f"Unknown playlist merge mode: {mode}")


def build_sync_plan(
    left: PlaylistData,
    right: PlaylistData,
    *,
    mode: PlaylistMergeMode = "union",
) -> PlaylistSyncPlan:
    """Build desired membership keys for both sides.

    This supports two practical workflows:
    - union: both sides converge to the same superset
    - directional set: one side is source-of-truth copied to the other
    """

    if mode == "union":
        merged = merge_membership_keys(left, right, mode=mode)
        return PlaylistSyncPlan(left_desired_keys=merged, right_desired_keys=merged)

    if mode == "left_to_right":
        return PlaylistSyncPlan(
            left_desired_keys=_dedupe_preserve_order(membership_keys(left)),
            right_desired_keys=merge_membership_keys(left, right, mode=mode),
        )

    if mode == "right_to_left":
        return PlaylistSyncPlan(
            left_desired_keys=merge_membership_keys(left, right, mode=mode),
            right_desired_keys=_dedupe_preserve_order(membership_keys(right)),
        )

    raise ValueError(f"Unknown playlist merge mode: {mode}")


def normalize_playlist_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def playlists_match_by_name(left: PlaylistData, right: PlaylistData) -> bool:
    """Basic cross-source matcher: normalized exact name equality."""

    return normalize_playlist_name(left.name) == normalize_playlist_name(right.name)
