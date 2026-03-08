from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Tuple

from beetsplug.muziekmachine.domain.models import (
    PullPlaylistsBatch,
    PullSongsBatch,
    PullSourceResult,
    SourceRef,
)
from beetsplug.muziekmachine.services.playlist_ingestion import (
    iter_collection_stubs,
    iter_playlist_data,
)
from beetsplug.muziekmachine.sources.base.adapter import MappingError


def pull_source(
    client,
    adapter,
    *,
    playlist: Optional[Sequence[str]] = None,
) -> Iterable[Tuple[Any, SourceRef]]:
    """Backward-compatible iterator of mapped songs for selected playlists."""

    result = pull_source_batch(client, adapter, selectors=playlist)
    yield from result.entries


def pull_source_batch(
    client,
    adapter,
    *,
    selectors: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> PullSongsBatch:
    """Pull mapped songs into an in-memory batch with per-source summary metrics."""

    source_name = getattr(adapter, "source", "unknown")
    result = PullSourceResult(source=source_name)
    entries: list[tuple[Any, SourceRef]] = []
    seen_external_ids: set[str] = set()

    collections = list(iter_collection_stubs(client, selectors=selectors))
    result.playlists_scanned = len(collections)

    for coll in collections:
        for raw in client.iter_items(coll):
            result.songs_seen += 1
            try:
                songdata = adapter.to_songdata(raw)
                ref = adapter.make_ref(raw, extra_keys={"collection_id": coll.id, "collection_name": coll.name})
            except MappingError:
                result.mapping_failures += 1
                continue
            except Exception as exc:
                result.mapping_failures += 1
                result.errors.append(str(exc))
                continue

            result.songs_mapped += 1
            if ref.external_id:
                if ref.external_id in seen_external_ids:
                    result.duplicates_observed += 1
                else:
                    seen_external_ids.add(ref.external_id)

            entries.append((songdata, ref))

            if limit is not None and result.songs_mapped >= limit:
                return PullSongsBatch(result=result, entries=entries)

    return PullSongsBatch(result=result, entries=entries)


def pull_playlists_batch(
    client,
    adapter,
    *,
    selectors: Optional[Sequence[str]] = None,
    include_items: bool = False,
    limit: Optional[int] = None,
) -> PullPlaylistsBatch:
    """Pull playlist objects into an in-memory batch with summary metrics."""

    source_name = getattr(adapter, "source", "unknown")
    result = PullSourceResult(source=source_name)
    playlists = []

    for playlist in iter_playlist_data(
        client,
        adapter,
        selectors=selectors,
        include_items=include_items,
    ):
        result.playlists_scanned += 1
        playlists.append(playlist)

        if limit is not None and result.playlists_scanned >= limit:
            break

    return PullPlaylistsBatch(result=result, playlists=playlists)
