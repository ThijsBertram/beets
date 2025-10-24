# sources/spotify/playlist_adapter.py
from typing import Any, Dict, List, Mapping, Optional
from adapters.playlist_base import PlaylistAdapter
from domain.models import PlaylistData, PlaylistRef, SongPointer

class SpotifyPlaylistAdapter(PlaylistAdapter):
    source = "spotify"

    def make_ref(self, raw_playlist: Dict[str, Any]) -> PlaylistRef:
        return PlaylistRef(source="spotify", id=raw_playlist["playlist_id"])

    def render_current_fields(self, raw_playlist: Dict[str, Any]) -> Mapping[str, Any]:
        return {
            "name": raw_playlist["playlist_name"],
            "description": raw_playlist.get("playlist_description") or "",
            "public": raw_playlist.get("public", None),
        }

    def render_desired_fields(self, pd: PlaylistData) -> Mapping[str, Any]:
        return {
            "name": pd.name,
            "description": pd.description or "",
            "public": pd.is_public,
        }

    def render_current_members(self, raw_items: List[Dict[str, Any]]) -> List[str]:
        # keys for membership diff; before matching we can key by ("spotify", track_id)
        return [f"spotify:{it['track']['id']}" for it in raw_items if it.get("track")]

    def render_desired_members(self, pd: PlaylistData) -> List[str]:
        keys = []
        for sp in pd.members or []:
            if sp.song_id:
                keys.append(f"song:{sp.song_id}")     # canonical songs after matching
            else:
                ref = sp.source_ref or {}
                keys.append(f"{ref.get('source')}:{ref.get('id')}")
        return keys

    def field_capabilities(self) -> set[str]:
        return {"name","description","public"}

    def membership_capabilities(self) -> set[str]:
        return {"add","remove","move"}
