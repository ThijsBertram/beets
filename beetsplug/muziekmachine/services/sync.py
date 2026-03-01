from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from beetsplug.muziekmachine.domain.models import SongData
from beetsplug.muziekmachine.domain.matching import find_potential_matches
from beetsplug.muziekmachine.domain.merging import merge_into_beets


@dataclass(frozen=True)
class MergePipelineResult:
    """Result for one incoming song representation through thin merge pipeline."""

    canonical_beets_id: int
    matched_beets_ids: List[int] = field(default_factory=list)
    source: str = ""



def _collect_representations_for_merge(
    lib,
    source: str,
    song: SongData,
    *,
    threshold: float,
    case_insensitive: bool,
    max_matches: int,
) -> List[Tuple[str, SongData, Optional[int]]]:
    """Build `(source, SongData, beets_id)` representations for merge.

    Includes the incoming representation and any matched canonical beets candidates.
    """

    matched = find_potential_matches(
        song,
        lib,
        threshold=threshold,
        case_insensitive=case_insensitive,
        limit=max_matches,
    )

    representations: List[Tuple[str, SongData, Optional[int]]] = [(source, song, None)]
    matched_ids: List[int] = []
    for beets_id, _score in matched[:max_matches]:
        item = lib.get_item(int(beets_id))
        if not item:
            continue
        representations.append(("beets", SongData.from_beets(item), int(beets_id)))
        matched_ids.append(int(beets_id))

    return representations



def merge_incoming_song(
    lib,
    source: str,
    song: SongData,
    *,
    precedence_config: Dict[str, Sequence[str]],
    threshold: float = 0.95,
    case_insensitive: bool = True,
    max_matches: int = 20,
    keep_beets_id: Optional[int] = None,
) -> MergePipelineResult:
    """Thin identity+merge pipeline for one incoming song representation.

    Steps:
    1) find potential matches in beets,
    2) build merge representations (incoming + matched beets songs),
    3) persist canonical merge/deprecate+rewire using `merge_into_beets`.
    """

    representations = _collect_representations_for_merge(
        lib,
        source,
        song,
        threshold=threshold,
        case_insensitive=case_insensitive,
        max_matches=max_matches,
    )

    if all(beets_id is None for _, _, beets_id in representations):
        raise ValueError(
            "No canonical beets candidate found for incoming song; "
            "create/import beets item first before merge_incoming_song."
        )

    canonical_id = merge_into_beets(
        lib,
        representations,
        precedence_config=precedence_config,
        keep_beets_id=keep_beets_id,
    )

    matched_ids = [int(bid) for _, _, bid in representations if bid is not None]
    return MergePipelineResult(
        canonical_beets_id=int(canonical_id),
        matched_beets_ids=sorted(set(matched_ids)),
        source=source,
    )



def merge_incoming_batch(
    lib,
    incoming: Sequence[Tuple[str, SongData]],
    *,
    precedence_config: Dict[str, Sequence[str]],
    threshold: float = 0.95,
    case_insensitive: bool = True,
    max_matches: int = 20,
) -> List[MergePipelineResult]:
    """Run thin identity+merge pipeline for a batch of incoming songs."""

    results: List[MergePipelineResult] = []
    for source, song in incoming:
        result = merge_incoming_song(
            lib,
            source,
            song,
            precedence_config=precedence_config,
            threshold=threshold,
            case_insensitive=case_insensitive,
            max_matches=max_matches,
        )
        results.append(result)
    return results
