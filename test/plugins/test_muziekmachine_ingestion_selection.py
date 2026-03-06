from __future__ import annotations

from beetsplug.muziekmachine.domain.models import CollectionStub
from beetsplug.muziekmachine.services.ingestion import pull_source


class _FakeClient:
    def iter_collections(self):
        yield CollectionStub(id="1", name="Deep House Essentials", raw={}, description="")
        yield CollectionStub(id="2", name="Techno", raw={}, description="")

    def iter_items(self, collection):
        if collection.id == "1":
            yield {"track": {"id": "s1"}}
        if collection.id == "2":
            yield {"track": {"id": "s2"}}


class _FakeAdapter:
    def to_songdata(self, raw):
        return raw["track"]["id"]

    def make_ref(self, raw):
        return raw["track"]["id"]


def test_pull_source_playlist_selector_uses_partial_name_matching():
    out = list(pull_source(_FakeClient(), _FakeAdapter(), playlist=["house"]))
    assert out == [("s1", "s1")]
