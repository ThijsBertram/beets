from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Sequence, Tuple

from beetsplug.muziekmachine.domain.matching import find_potential_matches, is_match, match_score
from beetsplug.muziekmachine.domain.models import (
    PlaylistData,
    PullPlaylistsBatch,
    PullSongsBatch,
    SongData,
    SourceRef,
)
from beetsplug.muziekmachine.domain.playlist_merge import normalize_playlist_name


@dataclass(frozen=True)
class CanonicalSong:
    """A canonical song identity for this run.

    - `canonical_key` is stable within one phase-2 run.
    - `beets_id` is set when we matched to an existing beets item.
    """

    canonical_key: str
    song: SongData
    beets_id: Optional[int] = None


@dataclass(frozen=True)
class SongAssignment:
    """Mapping from one source song pointer to one canonical song identity."""

    source_ref: SourceRef
    canonical_key: str
    confidence: float


@dataclass
class SongMatchPlan:
    """Song-level diff/match output for one pull run."""

    canonicals: Dict[str, CanonicalSong] = field(default_factory=dict)
    assignments: list[SongAssignment] = field(default_factory=list)

    def canonical_for_ref(self, ref: SourceRef) -> Optional[str]:
        for assignment in self.assignments:
            if assignment.source_ref == ref:
                return assignment.canonical_key
        return None


@dataclass(frozen=True)
class PlaylistTargetPlan:
    """Per-playlist desired canonical membership for a source playlist."""

    source: str
    playlist_id: str
    playlist_name: str
    desired_keys: list[str]


@dataclass
class PlaylistMatchPlan:
    """Playlist-level diff/match output for one pull run."""

    targets: list[PlaylistTargetPlan] = field(default_factory=list)


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _source_platform_pairs(song: SongData, ref: SourceRef) -> list[Tuple[str, str]]:
    pairs: list[Tuple[str, str]] = []

    if ref.source == "spotify" and ref.external_id:
        pairs.append(("spotify_id", ref.external_id))
    if ref.source == "youtube" and ref.external_id:
        pairs.append(("youtube_id", ref.external_id))

    if song.spotify_id:
        pairs.append(("spotify_id", song.spotify_id))
    if song.youtube_id:
        pairs.append(("youtube_id", song.youtube_id))
    if song.soundcloud_id:
        pairs.append(("soundcloud_id", song.soundcloud_id))
    if song.rekordbox_id:
        pairs.append(("rekordbox_id", song.rekordbox_id))

    unique_pairs: list[Tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field, value in pairs:
        marker = (field, str(value))
        if marker in seen:
            continue
        seen.add(marker)
        unique_pairs.append((field, str(value)))
    return unique_pairs


def _find_beets_item_by_platform_id(lib, song: SongData, ref: SourceRef) -> Optional[int]:
    """Find an existing beets item by strict source/platform id fields."""

    pairs = _source_platform_pairs(song, ref)
    if not pairs:
        return None

    for item in lib.items():
        for field, value in pairs:
            if getattr(item, field, None) and str(getattr(item, field)) == str(value):
                return int(item.id)
    return None


def _playlist_id_from_data(source: str, playlist: PlaylistData) -> Optional[str]:
    if source == "spotify":
        return playlist.spotify_id
    if source == "youtube":
        return playlist.youtube_id
    if source == "beets":
        return playlist.beets_id
    if source == "rekordbox":
        return playlist.rekordbox_id
    if source == "filesystem":
        return playlist.filesystem_id
    return None


def build_song_match_plan(
    song_batches: Sequence[PullSongsBatch],
    lib,
    *,
    threshold: float = 0.95,
) -> SongMatchPlan:
    """Build canonical song assignments from pulled source songs.

    Matching strategy (in order):
    1. strict platform-id match against beets,
    2. metadata candidate match against beets via matching service,
    3. in-memory canonical match against new canonicals from this run,
    4. create new in-memory canonical.
    """

    plan = SongMatchPlan()
    memory_canonicals: dict[str, SongData] = {}
    next_memory_id = 1

    for batch in song_batches:
        for song, ref in batch.entries:
            beets_id = _find_beets_item_by_platform_id(lib, song, ref)
            if beets_id is not None:
                canonical_key = f"song:{beets_id}"
                if canonical_key not in plan.canonicals:
                    plan.canonicals[canonical_key] = CanonicalSong(
                        canonical_key=canonical_key,
                        beets_id=beets_id,
                        song=song,
                    )
                plan.assignments.append(
                    SongAssignment(source_ref=ref, canonical_key=canonical_key, confidence=1.0)
                )
                continue

            beets_matches = find_potential_matches(song, lib, threshold=threshold)
            if beets_matches:
                # Deterministic tie-break: score desc, then beets id asc.
                beets_id, score = sorted(beets_matches, key=lambda m: (-m[1], m[0]))[0]
                canonical_key = f"song:{beets_id}"
                if canonical_key not in plan.canonicals:
                    plan.canonicals[canonical_key] = CanonicalSong(
                        canonical_key=canonical_key,
                        beets_id=beets_id,
                        song=song,
                    )
                plan.assignments.append(
                    SongAssignment(source_ref=ref, canonical_key=canonical_key, confidence=score)
                )
                continue

            memory_candidates = []
            for key, candidate in memory_canonicals.items():
                decision = is_match(song, candidate, threshold=threshold)
                if decision.is_match:
                    memory_candidates.append((key, match_score(song, candidate, threshold=threshold)))

            if memory_candidates:
                canonical_key, score = sorted(memory_candidates, key=lambda m: (-m[1], m[0]))[0]
                plan.assignments.append(
                    SongAssignment(source_ref=ref, canonical_key=canonical_key, confidence=score)
                )
                continue

            canonical_key = f"mem:{next_memory_id}"
            next_memory_id += 1
            memory_canonicals[canonical_key] = song
            plan.canonicals[canonical_key] = CanonicalSong(
                canonical_key=canonical_key,
                beets_id=None,
                song=song,
            )
            plan.assignments.append(
                SongAssignment(source_ref=ref, canonical_key=canonical_key, confidence=1.0)
            )

    return plan


def build_playlist_match_plan(
    playlist_batches: Sequence[PullPlaylistsBatch],
    song_plan: SongMatchPlan,
) -> PlaylistMatchPlan:
    """Build playlist membership targets by matching playlists on normalized name.

    Default policy is additive/cumulative: each matched same-name playlist receives
    the union of all canonical keys seen for that name across sources.
    """

    # Membership observed during song pull, grouped by concrete source playlist.
    per_playlist_members: dict[tuple[str, str], list[str]] = defaultdict(list)
    for assignment in song_plan.assignments:
        ref = assignment.source_ref
        if not ref.collection_id:
            continue
        per_playlist_members[(ref.source, ref.collection_id)].append(assignment.canonical_key)

    # Group concrete playlists by normalized name (name-only matching policy).
    groups: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for batch in playlist_batches:
        source = batch.result.source
        for playlist in batch.playlists:
            playlist_id = _playlist_id_from_data(source, playlist)
            if not playlist_id:
                continue
            norm_name = normalize_playlist_name(playlist.name)
            groups[norm_name].append((source, playlist_id, playlist.name))

    targets: list[PlaylistTargetPlan] = []
    for _norm_name, concrete_playlists in sorted(groups.items(), key=lambda item: item[0]):
        union_keys: list[str] = []
        for source, playlist_id, _playlist_name in concrete_playlists:
            union_keys.extend(per_playlist_members.get((source, playlist_id), []))
        desired = _dedupe_preserve_order(union_keys)

        for source, playlist_id, playlist_name in concrete_playlists:
            targets.append(
                PlaylistTargetPlan(
                    source=source,
                    playlist_id=playlist_id,
                    playlist_name=playlist_name,
                    desired_keys=desired,
                )
            )

    targets.sort(key=lambda t: (normalize_playlist_name(t.playlist_name), t.source, t.playlist_id))
    return PlaylistMatchPlan(targets=targets)
