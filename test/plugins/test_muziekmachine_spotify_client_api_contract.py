from __future__ import annotations

from beetsplug.muziekmachine.domain.models import CollectionStub
from beetsplug.muziekmachine.sources.spotify.client import SpotifyClient


class _FakeAPI:
    def __init__(self):
        self.calls = []

    def playlist_items(self, playlist_id, limit=50, offset=0, additional_types=("track",)):
        self.calls.append(("playlist_items", playlist_id, limit, offset, additional_types))
        return {"items": [{"track": {"id": "t1"}}], "next": None}

    def current_user_playlist_create(self, name, public=True, description=""):
        self.calls.append(("current_user_playlist_create", name, public, description))
        return {"id": "pl1", "name": name, "description": description}

    def search(self, q, type="track", limit=10):
        self.calls.append(("search", q, type, limit))
        return {"tracks": {"items": []}}



def _client_with_api(api: _FakeAPI) -> SpotifyClient:
    c = SpotifyClient(client_id="x", client_secret="y", redirect_uri="z")
    c.api = api
    return c


def test_iter_items_uses_playlist_items_endpoint_shape():
    api = _FakeAPI()
    c = _client_with_api(api)

    items = list(c.iter_items(CollectionStub(id="pl1", name="n", raw={}, description="")))

    assert items == [{"track": {"id": "t1"}}]
    assert api.calls[0][0] == "playlist_items"


def test_create_collection_uses_current_user_playlist_create():
    api = _FakeAPI()
    c = _client_with_api(api)

    stub = c.create_collection("Name", description="Desc", public=False)

    assert stub.id == "pl1"
    assert api.calls[0][0] == "current_user_playlist_create"


def test_search_song_candidates_clamps_limit_to_10():
    api = _FakeAPI()
    c = _client_with_api(api)

    list(c.search_song_candidates(type("SD", (), {"title": "A", "main_artist": "B"})(), limit=100))

    assert api.calls[0] == ("search", "track:A artist:B", "track", 10)
