from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional

from beetsplug.muziekmachine.sources.base.playlist_adapter import PlaylistAdapter
from beetsplug.muziekmachine.domain.models import PlaylistData, PlaylistRef, SongPointer, CollectionStub
from beetsplug.muziekmachine.sources.youtube.playlist_mapper import YouTubePlaylistMapper


class YouTubePlaylistAdapter(PlaylistAdapter):
    source = "youtube"

    # ── identity from a CollectionStub ───────────────────────────────────────
    def collection_id(self, stub: CollectionStub) -> str:
        return stub.id

    def collection_name(self, stub: CollectionStub) -> str:
        return stub.name

    def make_ref(self, stub: CollectionStub) -> PlaylistRef:
        return PlaylistRef(source="youtube", playlist_id=stub.id)

    # ── PlaylistData mapping (from stub) ─────────────────────────────────────
    def to_playlistdata(self, stub: CollectionStub, raw_items=None) -> PlaylistData:
        mapper = YouTubePlaylistMapper()
        return mapper.to_playlistdata(stub=stub)

    # ── field projections ───────────────────────────────────────────────────
    def render_current_fields(self, raw_playlist: Dict[str, Any]) -> Mapping[str, Any]:
        snippet = raw_playlist.get("snippet", {})
        status = raw_playlist.get("status", {})
        return {
            "name": snippet.get("title"),
            "description": snippet.get("description") or "",
            "public": status.get("privacyStatus") == "public",
        }

    def render_desired_fields(self, pd: PlaylistData) -> Mapping[str, Any]:
        return {
            "name": pd.name,
            "description": pd.description or "",
            "public": pd.is_public,
        }

    # ── membership projections ───────────────────────────────────────────────
    def render_current_members(self, raw_items: List[Dict[str, Any]]) -> List[str]:
        keys = []
        for it in raw_items:
            cd = it.get("contentDetails") or {}
            vid = cd.get("videoId")
            if vid:
                keys.append(f"youtube:{vid}")
        return keys

    def render_desired_members(self, pd: PlaylistData) -> List[str]:
        keys: List[str] = []
        for sp in pd.members or []:
            if sp.song_id:
                keys.append(f"song:{sp.song_id}")
            else:
                ref = sp.source_ref or {}
                if ref.get("source") == "youtube":
                    external_id = ref.get("external_id") or ref.get("id")
                    if external_id:
                        keys.append(f"youtube:{external_id}")
        return keys

    # ── capabilities ────────────────────────────────────────────────────────
    def field_capabilities(self) -> set[str]:
        # You *can* update playlist name/description/public on YT via API, but keep read-only
        # until you want to implement client-side write calls.
        return set()

    def membership_capabilities(self) -> set[str]:
        # Similarly, YouTube supports insert/delete playlistItems; leave read-only for now.
        return set()
