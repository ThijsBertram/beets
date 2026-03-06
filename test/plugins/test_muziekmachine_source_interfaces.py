from __future__ import annotations

from beetsplug.muziekmachine.services.playlist_ingestion import iter_collection_stubs
from beetsplug.muziekmachine.domain.models import CollectionStub, PlaylistData
from beetsplug.muziekmachine.sources.spotify.playlist_adapter import SpotifyPlaylistAdapter


class _FakeClient:
    def iter_collections(self):
        yield CollectionStub(id="1", name="Deep House Essentials", raw={}, description="")
        yield CollectionStub(id="2", name="Techno", raw={}, description="")


def test_iter_collection_stubs_supports_partial_name_match():
    client = _FakeClient()
    names = [stub.name for stub in iter_collection_stubs(client, selectors=["house"]) ]
    assert names == ["Deep House Essentials"]


def test_spotify_playlist_adapter_current_fields_match_spotify_shape():
    adapter = SpotifyPlaylistAdapter()
    raw_playlist = {"name": "My List", "description": "desc", "public": True}
    assert adapter.render_current_fields(raw_playlist) == {
        "name": "My List",
        "description": "desc",
        "public": True,
    }


def test_spotify_playlist_adapter_desired_members_uses_external_id():
    adapter = SpotifyPlaylistAdapter()
    desired = PlaylistData(name="x", members=[])
    assert adapter.render_desired_members(desired) == []
