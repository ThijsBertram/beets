from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Tuple

from beetsplug.muziekmachine.domain.models import SourceRef
from beetsplug.muziekmachine.services.playlist_ingestion import iter_collection_stubs
from beetsplug.muziekmachine.sources.base.adapter import MappingError


def pull_source(
    client,
    adapter,
    *,
    playlist: Optional[Sequence[str]] = None,
) -> Iterable[Tuple[Any, SourceRef]]:
    """Iterate a source and yield (SongData, SourceRef) pairs.

    `playlist` selectors are matched consistently via `iter_collection_stubs`
    (supports exact id, exact name, and partial-name matching).
    """

    def emit(raw):
        try:
            songdata = adapter.to_songdata(raw)
            ref = adapter.make_ref(raw)
        except MappingError:
            print(f"UNABLE TO PARSE ENTRY:\n{raw}\n")
            return None, None
        return songdata, ref

    # FETCH ITEMS FOR SPECIFIC PLAYLISTS / COLLECTIONS
    if playlist:
        for coll in iter_collection_stubs(client, selectors=playlist):
            for raw in client.iter_items(coll):
                songdata, ref = emit(raw)
                if songdata:
                    yield songdata, ref
        return

    # FETCH ALL ITEMS
    if getattr(client, "supports_global_items", lambda: False)():
        for raw in client.iter_items_global():
            songdata, ref = emit(raw)
            if songdata:
                yield songdata, ref
    else:
        for coll in client.iter_collections():
            for raw in client.iter_items(coll):
                songdata, ref = emit(raw)
                if songdata:
                    yield songdata, ref
