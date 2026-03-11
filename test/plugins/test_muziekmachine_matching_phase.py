from __future__ import annotations

from types import SimpleNamespace

from beetsplug.muziekmachine.domain.models import (
    PlaylistData,
    PullPlaylistsBatch,
    PullSongsBatch,
    PullSourceResult,
    SongData,
    SourceRef,
)
from beetsplug.muziekmachine.services.matching_phase import (
    SongAssignment,
    SongMatchPlan,
    build_playlist_match_plan,
    build_song_match_plan,
)


class _FakeLib:
    def __init__(self, items):
        self._items = items

    def items(self, query=None):
        return iter(self._items)


def _batch(source: str, entries):
    return PullSongsBatch(result=PullSourceResult(source=source), entries=list(entries))


def test_song_matching_prefers_strict_platform_id_match_to_beets():
    lib = _FakeLib([SimpleNamespace(id=10, spotify_id="sp-1", youtube_id=None, title="Anything", artist="Anyone")])

    song = SongData(title="Unknown title", main_artist="Unknown artist", spotify_id="sp-1")
    ref = SourceRef(source="spotify", external_id="sp-1", collection_id="pl-1")

    plan = build_song_match_plan([_batch("spotify", [(song, ref)])], lib)

    assert len(plan.assignments) == 1
    assert plan.assignments[0].canonical_key == "song:10"
    assert plan.assignments[0].confidence == 1.0
    assert plan.canonicals["song:10"].beets_id == 10


def test_song_matching_falls_back_to_in_memory_canonical_when_beets_has_no_match():
    lib = _FakeLib([])

    song1 = SongData(title="Track Name", main_artist="Artist Name")
    song2 = SongData(title="Track Name", main_artist="Artist Name")

    ref1 = SourceRef(source="spotify", external_id="sp-1", collection_id="pl-1")
    ref2 = SourceRef(source="youtube", external_id="yt-1", collection_id="pl-2")

    plan = build_song_match_plan([
        _batch("spotify", [(song1, ref1)]),
        _batch("youtube", [(song2, ref2)]),
    ], lib)

    assert [assignment.canonical_key for assignment in plan.assignments] == ["mem:1", "mem:1"]
    assert "mem:1" in plan.canonicals
    assert plan.canonicals["mem:1"].beets_id is None


def test_playlist_matching_is_name_based_and_additive():
    song_plan = SongMatchPlan(
        assignments=[
            SongAssignment(
                source_ref=SourceRef(source="spotify", external_id="sp-1", collection_id="pl-sf"),
                canonical_key="song:10",
                confidence=1.0,
            ),
            SongAssignment(
                source_ref=SourceRef(source="youtube", external_id="yt-1", collection_id="pl-yt"),
                canonical_key="mem:1",
                confidence=1.0,
            ),
        ]
    )

    playlist_batches = [
        PullPlaylistsBatch(
            result=PullSourceResult(source="spotify"),
            playlists=[PlaylistData(name="My Playlist", spotify_id="pl-sf")],
        ),
        PullPlaylistsBatch(
            result=PullSourceResult(source="youtube"),
            playlists=[PlaylistData(name="my playlist", youtube_id="pl-yt")],
        ),
    ]

    plan = build_playlist_match_plan(playlist_batches, song_plan)

    assert len(plan.targets) == 2
    assert plan.targets[0].desired_keys == ["song:10", "mem:1"]
    assert plan.targets[1].desired_keys == ["song:10", "mem:1"]
