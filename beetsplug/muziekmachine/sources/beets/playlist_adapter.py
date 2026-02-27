from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional

from beetsplug.muziekmachine.sources.base.playlist_adapter import PlaylistAdapter
from beetsplug.muziekmachine.sources.beets.mapper import BeetsMapper
from beetsplug.muziekmachine.sources.beets.playlist_mapper import BeetsPlaylistMapper
from beetsplug.muziekmachine.domain.models import PlaylistData, PlaylistRef, CollectionStub


class BeetsPlaylistAdapter(PlaylistAdapter):
    source = "beets"

    def __init__(self, client, mapper: BeetsMapper | None = None) -> None:
        self.client = client
        self.mapper = mapper or BeetsMapper()

    # ================
    # IDENTITY
    # ================
    def collection_id(self, row: Dict[str, Any]) -> str:
        return str(row.get("id"))
    
    def collection_name(self, row: Dict[str, Any]) -> str:
        return str(row.get("name"))
    
    def make_ref(self, row: Dict[str, Any]) -> PlaylistRef:
        return PlaylistRef(source="beets", id=str(row["id"]))
    

    # ================
    # TO PLAYLISTDATA
    # ================

    def to_playlistdata(self, stub: CollectionStub, raw_items=None) -> PlaylistData:
        mapper = BeetsPlaylistMapper()
        playlist_data = mapper.to_playlistdata(stub=stub, raw_items=raw_items)
        return playlist_data

    # ================
    # RENDERING
    # ================

    def render_current_fields(self, row: Dict[str, Any]) -> Mapping[str, Any]:
        return {
            "name": row["name"],
            "description": row.get("description") or "",
            "type": row.get("type") or "",
        }

    def render_desired_fields(self, pd: PlaylistData) -> Mapping[str, Any]:
        return {
            "name": pd.name,
            "description": pd.description or "",
            "type": getattr(pd, "type", "") or "",
        }

    def render_current_members(self, raw_items: List[Any]) -> List[str]:
        # For membership diffs, key by canonical song id when available; for Beets, we key by beets item id
        return [f"beets:{it.id}" for it in raw_items]

    def render_desired_members(self, pd: PlaylistData) -> List[str]:
        keys = []
        for sp in (pd.members or []):
            if sp.song_id:
                keys.append(f"song:{sp.song_id}")
            else:
                ref = sp.source_ref or {}
                if ref.get("source") == "beets" and ref.get("id"):
                    keys.append(f"beets:{ref['id']}")
                else:
                    # fallback: unresolved; you may skip or handle separately
                    pass
        return keys

    def field_capabilities(self) -> set[str]:
        return {"name","description","type"}

    def membership_capabilities(self) -> set[str]:
        return {"add","remove","move"}