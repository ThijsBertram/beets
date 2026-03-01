from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

from beets.dbcore import AndQuery
from beets.dbcore.query import MatchQuery, SubstringQuery

from beetsplug.muziekmachine.domain.models import SongData


@dataclass(frozen=True)
class MatchResult:
    """Simple match result for two SongData objects."""

    is_match: bool
    score: float


def _norm_text(value: Optional[str], *, case_insensitive: bool = True) -> str:
    text = (value or "").strip()
    return text.lower() if case_insensitive else text


def _ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _field_match(a: Optional[str], b: Optional[str], *, threshold: float, case_insensitive: bool) -> bool:
    """Field-level match rule: if both values are present they must match >= threshold.

    If either side is missing, this function returns True (unknown, not conflicting).
    """

    left = _norm_text(a, case_insensitive=case_insensitive)
    right = _norm_text(b, case_insensitive=case_insensitive)
    if not left or not right:
        return True
    return _ratio(left, right) >= threshold


def match_score(
    song_a: SongData,
    song_b: SongData,
    *,
    case_insensitive: bool = True,
    threshold: float = 0.95,
) -> float:
    """Return fraction of identity fields that pass threshold-based matching.

    Identity fields: main_artist, title, feat_artist, remixer, remix_type.
    """

    checks = [
        _field_match(song_a.main_artist, song_b.main_artist, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.title, song_b.title, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.feat_artist, song_b.feat_artist, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.remixer, song_b.remixer, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.remix_type, song_b.remix_type, threshold=threshold, case_insensitive=case_insensitive),
    ]
    return sum(1.0 for ok in checks if ok) / len(checks)


def is_match(
    song_a: SongData,
    song_b: SongData,
    *,
    threshold: float = 0.95,
    case_insensitive: bool = True,
) -> MatchResult:
    """True when all identity-field checks pass at the provided fuzzy threshold."""

    checks = [
        _field_match(song_a.main_artist, song_b.main_artist, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.title, song_b.title, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.feat_artist, song_b.feat_artist, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.remixer, song_b.remixer, threshold=threshold, case_insensitive=case_insensitive),
        _field_match(song_a.remix_type, song_b.remix_type, threshold=threshold, case_insensitive=case_insensitive),
    ]

    all_match = all(checks)
    return MatchResult(is_match=all_match, score=(1.0 if all_match else match_score(song_a, song_b, threshold=threshold, case_insensitive=case_insensitive)))


def _build_beets_candidate_query(song: SongData):
    """Build a narrowed beets query for candidate retrieval.

    Strategy:
    - prefer exact artist match when present,
    - and title substring filter when present.
    """

    parts = []
    if song.main_artist:
        parts.append(MatchQuery("artist", song.main_artist))
    if song.title:
        parts.append(SubstringQuery("title", song.title))

    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return AndQuery(parts)


def find_potential_matches(
    song: SongData,
    lib,
    *,
    threshold: float = 0.95,
    case_insensitive: bool = True,
    limit: int = 200,
) -> List[Tuple[int, float]]:
    """Query beets for candidate items and return matching `(beets_id, score)` pairs.

    This function performs its own candidate retrieval from beets, then applies
    strict identity matching (`is_match`) on SongData projections.
    """

    query = _build_beets_candidate_query(song)
    iterator = lib.items(query) if query is not None else lib.items()

    matches: List[Tuple[int, float]] = []
    for idx, item in enumerate(iterator):
        if idx >= limit:
            break

        candidate = SongData.from_beets(item)
        decision = is_match(song, candidate, threshold=threshold, case_insensitive=case_insensitive)
        if decision.is_match:
            matches.append((int(item.id), decision.score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
