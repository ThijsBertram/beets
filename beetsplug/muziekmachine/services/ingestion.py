from __future__ import annotations
from typing import Iterable, Tuple, Any, Set, Optional, Sequence
from beetsplug.muziekmachine.domain.models import SourceRef
from beetsplug.muziekmachine.sources.base.errors import *
from beetsplug.muziekmachine.sources.base.adapter import *

def pull_source(client, adapter, *, playlist: Optional[Sequence[str]]) -> Iterable[Tuple[Any, SourceRef]]:
    """
    Iterate a source (Spotify) and yield (SongData, SourceRef) pairs.
    If `playlist` is provided, match by name or id.
    """

    def emit(raw):
        try:
            songdata = adapter.to_songdata(raw)
            ref = adapter.make_ref(raw)
        except MappingError:
            print(f'UNABLE TO PARSE ENTRY:\n{raw}\n')
            return None, None
        return songdata, ref
        
    # FETCH ITEMS FOR SPECIFIC PLAYLISTS / COLLECTIONS
    if playlist:
        wanted = playlist.split(',')

        for coll in client.iter_collections():
            if coll.id in wanted or coll.name in wanted:
                for raw in client.iter_items(coll):
                    songdata, ref = emit(raw)
                    if songdata:
                        yield songdata, ref
        return
    
    # FETCH ALL ITEMS 
    # use iter_items_global() if source supports it
    if getattr(client, "supports_global_items", lambda: False)():
        for raw in client.iter_items_global():
            songdata, ref = emit(raw)
            if songdata:
                yield songdata, ref
    # else loop over all collections/playlists and returnt items 
    else:
        for coll in client.iter_collections():
            for raw in client.iter_items(coll):
                songdata, ref = emit(raw)
                if songdata:
                    yield songdata, ref

