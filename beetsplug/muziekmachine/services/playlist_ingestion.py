from __future__ import annotations
from typing import Iterable, Tuple, Optional, Sequence, Dict, Any, List
from beetsplug.muziekmachine.domain.models import PlaylistRef, PlaylistData, SourceName, CollectionStub


def iter_collection_stubs(
    client,
    *,
    selectors: Optional[Sequence[str]] = None,  # names or ids; None/[] => ALL
) -> Iterable[CollectionStub]:
    want_all = not selectors
    wanted = set(map(str, selectors or []))

    for stub in client.iter_collections():
        pid = stub.id or ""              # id for matching
        pname = stub.name or ""              # name for matching
        if want_all or pid in wanted or pname in wanted:
            yield stub

def iter_playlist_data(
    client,
    adapter,
    *,
    selectors: Optional[Sequence[str]] = None,
    include_items: bool = False,
) -> Iterable[PlaylistData]:
    """
    Yield PlaylistData for each selected collection.
    - Uses CollectionStub directly (no raw peeking).
    - If include_items=True, fetch membership via client.iter_items(stub).
    """
    for stub in iter_collection_stubs(client, selectors=selectors):
        raw_items = list(client.iter_items(stub)) if include_items else None
        yield adapter.to_playlistdata(stub, raw_items)