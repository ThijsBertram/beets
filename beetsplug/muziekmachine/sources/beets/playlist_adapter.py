from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional

from beetsplug.muziekmachine.sources.base.playlist_adapter import PlaylistAdapter
from beetsplug.muziekmachine.sources.beets.mapper import BeetsMapper
from beetsplug.muziekmachine.domain.models import PlaylistData, PlaylistRef


class BeetsPlaylistAdapter(PlaylistAdapter):
    source = "beets"

    def __init__(self, client, mapper: BeetsMapper | None = None) -> None:
        self.client = client
        self.mapper = mapper or BeetsMapper()

    def make_ref(self, row: Dict[str, Any]) -> PlaylistRef:
        return PlaylistRef(source="beets", id=str(row["id"]))

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