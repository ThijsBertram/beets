from __future__ import annotations

import importlib.util
from pathlib import Path

from beetsplug.muziekmachine.domain.models import PlaylistData, SongPointer


_MODULE_PATH = Path(__file__).resolve().parents[2] / "beetsplug" / "muziekmachine" / "domain" / "playlist_merge.py"
_SPEC = importlib.util.spec_from_file_location("mm_playlist_merge", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_playlist_merge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_playlist_merge)

build_sync_plan = _playlist_merge.build_sync_plan
membership_keys = _playlist_merge.membership_keys
merge_membership_keys = _playlist_merge.merge_membership_keys
playlists_match_by_name = _playlist_merge.playlists_match_by_name


def _sp(song_id: str) -> SongPointer:
    return SongPointer(song_id=song_id)


def _src(source: str, external_id: str) -> SongPointer:
    return SongPointer(source_ref={"source": source, "external_id": external_id})


def test_membership_keys_supports_song_id_and_source_ref_dict():
    pd = PlaylistData(name="x", members=[_sp("1"), _src("spotify", "abc")])
    assert membership_keys(pd) == ["song:1", "spotify:abc"]


def test_merge_membership_keys_union_dedupes_and_preserves_order():
    left = PlaylistData(name="L", members=[_sp("1"), _sp("2"), _sp("1")])
    right = PlaylistData(name="R", members=[_sp("2"), _sp("3")])

    merged = merge_membership_keys(left, right, mode="union")

    assert merged == ["song:1", "song:2", "song:3"]


def test_build_sync_plan_union_sets_both_sides_to_union():
    left = PlaylistData(name="L", members=[_sp("1")])
    right = PlaylistData(name="R", members=[_sp("2")])

    plan = build_sync_plan(left, right, mode="union")

    assert plan.left_desired_keys == ["song:1", "song:2"]
    assert plan.right_desired_keys == ["song:1", "song:2"]


def test_build_sync_plan_left_to_right_only_changes_right():
    left = PlaylistData(name="L", members=[_sp("1"), _sp("2")])
    right = PlaylistData(name="R", members=[_sp("3")])

    plan = build_sync_plan(left, right, mode="left_to_right")

    assert plan.left_desired_keys == ["song:1", "song:2"]
    assert plan.right_desired_keys == ["song:1", "song:2"]


def test_build_sync_plan_right_to_left_only_changes_left():
    left = PlaylistData(name="L", members=[_sp("1")])
    right = PlaylistData(name="R", members=[_sp("2"), _sp("3")])

    plan = build_sync_plan(left, right, mode="right_to_left")

    assert plan.left_desired_keys == ["song:2", "song:3"]
    assert plan.right_desired_keys == ["song:2", "song:3"]


def test_playlists_match_by_name_ignores_case_and_extra_whitespace():
    left = PlaylistData(name="  Example   Playlist ")
    right = PlaylistData(name="example playlist")
    assert playlists_match_by_name(left, right)
