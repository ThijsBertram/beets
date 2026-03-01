from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[2] / "beetsplug" / "muziekmachine" / "domain" / "playlist_diffs.py"
_SPEC = importlib.util.spec_from_file_location("mm_playlist_diffs", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_playlist_diffs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_playlist_diffs)

compute_field_diff = _playlist_diffs.compute_field_diff
compute_membership_diff = _playlist_diffs.compute_membership_diff
MembershipOp = _playlist_diffs.MembershipOp


def test_compute_field_diff_treats_none_and_empty_string_as_equal():
    current = {"name": "House", "description": "", "public": None}
    desired = {"name": "House", "description": None, "public": ""}

    diff = compute_field_diff(current, desired)

    assert diff.changes == {}


def test_compute_field_diff_detects_real_changes():
    current = {"name": "Old", "description": "Warmup"}
    desired = {"name": "New", "description": "Warmup", "public": True}

    diff = compute_field_diff(current, desired)

    assert diff.changes == {
        "name": ("Old", "New"),
        "public": (None, True),
    }


def test_compute_membership_diff_removes_duplicates_and_reorders_deterministically():
    current = ["spotify:a", "spotify:b", "spotify:a", "spotify:c"]
    desired = ["spotify:c", "spotify:a", "spotify:c"]

    diff = compute_membership_diff(current, desired)

    assert diff.ops == [
        MembershipOp("remove", "spotify:a", 2),
        MembershipOp("remove", "spotify:b", 1),
        MembershipOp("move", "spotify:c", 0),
    ]


def test_compute_membership_diff_add_remove_and_move_plan():
    current = ["spotify:a", "spotify:b", "spotify:c"]
    desired = ["spotify:c", "spotify:d", "spotify:a"]

    diff = compute_membership_diff(current, desired)

    assert diff.ops == [
        MembershipOp("remove", "spotify:b", 1),
        MembershipOp("move", "spotify:c", 0),
        MembershipOp("add", "spotify:d", 1),
    ]


def test_compute_membership_diff_noop_when_already_equal():
    current = ["song:1", "song:2", "song:3"]
    desired = ["song:1", "song:2", "song:3"]

    diff = compute_membership_diff(current, desired)

    assert diff.ops == []
