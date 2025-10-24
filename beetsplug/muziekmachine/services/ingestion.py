from __future__ import annotations
from typing import Iterable, Tuple, Any
from beetsplug.muziekmachine.domain.models import SourceRef

def pull_source(client, adapter, *, playlist: str | None = None) -> Iterable[Tuple[Any, SourceRef]]:
    """
    Iterate a source (Spotify) and yield (SongData, SourceRef) pairs.
    If `playlist` is provided, match by name or id.
    """
    collections = client.iter_collections()
    for coll in collections:
        if playlist and playlist not in (coll["playlist_id"], coll["playlist_name"]):
            continue
        for raw in client.iter_items(coll):
            sd = adapter.to_songdata(raw)
            ref = adapter.make_ref(raw)
            yield sd, ref
