from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from beetsplug.muziekmachine.domain.models import SongData


def _is_present(value: Any) -> bool:
    return value is not None and value != ""


def _first_present_from_sources(
    field: str,
    by_source: Dict[str, SongData],
    precedence: Sequence[str],
) -> Any:
    for source in precedence:
        song = by_source.get(source)
        if not song:
            continue
        value = getattr(song, field, None)
        if _is_present(value):
            return value
    return None


def merge_song_representations(
    representations: Sequence[Tuple[str, SongData]],
    *,
    precedence_config: Dict[str, Sequence[str]],
    default_source_order: Sequence[str] = ("beets", "rekordbox", "spotify", "youtube", "filesystem"),
    keep_single_platform_id: bool = True,
) -> SongData:
    """Merge multiple source SongData representations into one canonical SongData."""

    if not representations:
        raise ValueError("merge_song_representations requires at least one representation")

    by_source: Dict[str, SongData] = {source: song for source, song in representations}

    # Start from first representation and resolve fields by precedence.
    merged_data = asdict(representations[0][1])

    fields_to_merge = [
        "title", "main_artist", "artists", "feat_artist",
        "album", "genre", "subgenre", "remixer", "remix_type",
        "bpm", "key", "comment", "path",
        "youtube_id", "spotify_id", "soundcloud_id",
        "rekordbox_id", "rekordbox_path", "rekordbox_bpm",
        "rekordbox_tonality", "rekordbox_comments", "rekordbox_rating", "rekordbox_cateogry",
    ]

    for field in fields_to_merge:
        precedence = precedence_config.get(field, default_source_order)
        chosen = _first_present_from_sources(field, by_source, precedence)
        if _is_present(chosen):
            merged_data[field] = chosen

    if keep_single_platform_id:
        # Single platform-id fields are already represented as singular attributes.
        pass

    return SongData(**merged_data)


def find_deprecated_beets_ids(beets_ids: Sequence[int], *, keep_id: Optional[int] = None) -> List[int]:
    """Return beets ids that should be marked deprecated after merge."""

    if not beets_ids:
        return []

    keep = keep_id if keep_id is not None else min(beets_ids)
    return [bid for bid in beets_ids if bid != keep]


def _apply_songdata_to_beets_item(item, song: SongData) -> None:
    """Persist merged canonical SongData fields onto a beets item."""

    item.title = song.title or item.title
    item.artist = song.main_artist or item.artist

    for src_field in [
        "genre", "bpm", "key", "youtube_id", "spotify_id", "soundcloud_id",
        "rekordbox_id", "rekordbox_path", "rekordbox_bpm", "rekordbox_tonality",
        "rekordbox_comments", "rekordbox_rating", "rekordbox_cateogry",
    ]:
        value = getattr(song, src_field, None)
        if _is_present(value):
            setattr(item, src_field, value)

    if _is_present(song.comment):
        item.comments = song.comment
    if _is_present(song.path):
        item.path = song.path


def reconcile_source_links(
    lib,
    canonical_id: int,
    duplicate_ids: Sequence[int],
    *,
    source_id_fields: Sequence[str] = (
        "youtube_id",
        "spotify_id",
        "soundcloud_id",
        "rekordbox_id",
        "rekordbox_path",
    ),
) -> None:
    """Ensure source-link ids are consolidated on canonical item and removed from deprecated duplicates."""

    canonical = lib.get_item(int(canonical_id))
    if not canonical:
        raise ValueError(f"canonical beets item id not found: {canonical_id}")

    changed_canonical = False

    for dup_id in duplicate_ids:
        duplicate = lib.get_item(int(dup_id))
        if not duplicate:
            continue

        changed_duplicate = False

        for field in source_id_fields:
            canonical_value = getattr(canonical, field, None)
            dup_value = getattr(duplicate, field, None)

            if _is_present(dup_value) and not _is_present(canonical_value):
                setattr(canonical, field, dup_value)
                changed_canonical = True

            if _is_present(dup_value):
                setattr(duplicate, field, None)
                changed_duplicate = True

        if changed_duplicate:
            duplicate.store()

    if changed_canonical:
        canonical.store()


def rewire_playlist_memberships(lib, canonical_id: int, duplicate_ids: Sequence[int]) -> None:
    """Rewire playlist membership rows from duplicates to canonical item id.

    Also removes resulting duplicate rows per playlist and re-compacts positions.
    """

    if not duplicate_ids:
        return

    conn = lib._connection()

    # 1) Point duplicate song memberships to canonical id.
    for dup_id in duplicate_ids:
        conn.execute(
            "UPDATE playlist_item SET item_id=? WHERE item_id=?",
            (int(canonical_id), int(dup_id)),
        )

    # 2) For each playlist, dedupe rows by item_id keeping earliest position.
    playlists = conn.execute("SELECT DISTINCT playlist_id FROM playlist_item").fetchall()
    for (playlist_id,) in playlists:
        rows = conn.execute(
            "SELECT item_id, position FROM playlist_item WHERE playlist_id=? ORDER BY position ASC",
            (playlist_id,),
        ).fetchall()

        seen_item_ids = set()
        kept_item_ids: List[int] = []
        for item_id, _position in rows:
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            kept_item_ids.append(item_id)

        # Replace playlist rows with deduped, compacted positions.
        conn.execute("DELETE FROM playlist_item WHERE playlist_id=?", (playlist_id,))
        for pos, item_id in enumerate(kept_item_ids):
            conn.execute(
                "INSERT INTO playlist_item(playlist_id, item_id, position) VALUES(?,?,?)",
                (playlist_id, item_id, pos),
            )

    conn.commit()


def merge_into_beets(
    lib,
    representations: Sequence[Tuple[str, SongData, Optional[int]]],
    *,
    precedence_config: Dict[str, Sequence[str]],
    keep_beets_id: Optional[int] = None,
    deprecated_field: str = "deprecated",
    replaced_by_field: str = "replaced_by_id",
) -> int:
    """Merge representations and persist result into beets.

    Returns
    -------
    int
        Canonical beets item id that now stores the merged song.
    """

    if not representations:
        raise ValueError("merge_into_beets requires at least one representation")

    merge_inputs = [(source, song) for source, song, _ in representations]
    merged = merge_song_representations(merge_inputs, precedence_config=precedence_config)

    beets_ids = [bid for _, _, bid in representations if bid is not None]
    if not beets_ids:
        raise ValueError("merge_into_beets requires at least one representation with a beets item id")

    canonical_id = keep_beets_id if keep_beets_id is not None else min(beets_ids)
    canonical_item = lib.get_item(int(canonical_id))
    if not canonical_item:
        raise ValueError(f"canonical beets item id not found: {canonical_id}")

    _apply_songdata_to_beets_item(canonical_item, merged)
    canonical_item[deprecated_field] = False
    canonical_item[replaced_by_field] = None
    canonical_item.store()

    duplicate_ids = find_deprecated_beets_ids(beets_ids, keep_id=canonical_id)

    # Ensure source ids are consolidated on canonical and cleared from duplicates.
    reconcile_source_links(lib, canonical_id, duplicate_ids)

    # Rewire all playlist memberships from duplicate rows to canonical id.
    rewire_playlist_memberships(lib, canonical_id, duplicate_ids)

    # Mark duplicates deprecated and linked to canonical replacement id.
    for dup_id in duplicate_ids:
        dup_item = lib.get_item(int(dup_id))
        if not dup_item:
            continue
        dup_item[deprecated_field] = True
        dup_item[replaced_by_field] = int(canonical_id)
        dup_item.store()

    return int(canonical_id)
