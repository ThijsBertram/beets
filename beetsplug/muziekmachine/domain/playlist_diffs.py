from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


# We treat playlist sync as two diffs:

    # Field diff for metadata (name/description/public)
    # Membership diff for ordered track list (add/remove/move)

# Adapters will implement the projection of playlists into these dicts/lists, exactly like with songs.



@dataclass
class FieldDiff:
    changes: Dict[str, Tuple[Any, Any]]   # e.g., {"name": ("Old","New"), "description": ("","...")}


@dataclass
class MembershipOp:
    op: str            # "add" | "remove" | "move"
    song_key: str      # stable key for a member (canonical song_id or a fallback composite)
    index: int         # target index for add/move (ignored for remove)


@dataclass
class MembershipDiff:
    ops: List[MembershipOp]


def compute_field_diff(current: Dict[str, Any], desired: Dict[str, Any]) -> FieldDiff:
    changes = {}
    for k in set(current) | set(desired):
        if current.get(k) != desired.get(k):
            changes[k] = (current.get(k), desired.get(k))
    return FieldDiff(changes)

def compute_field_diff(current: Dict[str, Any], desired: Dict[str, Any]) -> FieldDiff:
    changes = {}
    for k in set(current) | set(desired):
        if current.get(k) != desired.get(k):
            changes[k] = (current.get(k), desired.get(k))
    return FieldDiff(changes)

def compute_membership_diff(current_keys: List[str], desired_keys: List[str]) -> MembershipDiff:
    """
    Compute a minimal-ish sequence of add/remove/move to transform current -> desired.
    Keeps order. Greedy O(n)–O(n log n) approach good enough for playlists.
    """
    ops: List[MembershipOp] = []
    cur_index = {k: i for i, k in enumerate(current_keys)}
    desired_set = set(desired_keys)
    current_set = set(current_keys)

    # removals (those not desired anymore)
    for k in current_keys:
        if k not in desired_set:
            ops.append(MembershipOp("remove", k, -1))

    # additions / moves in order of desired
    seen = [k for k in current_keys if k in desired_set]  # surviving keys in current order
    i = 0
    for target_idx, key in enumerate(desired_keys):
        if i < len(seen) and seen[i] == key:
            # already in correct relative order; advance
            i += 1
        else:
            if key in current_set:
                # exists but out of place -> move
                ops.append(MembershipOp("move", key, target_idx))
                # Update 'seen' model cheaply
                if key in seen:
                    seen.remove(key)
                seen.insert(i, key)
                i += 1
            else:
                # new add
                ops.append(MembershipOp("add", key, target_idx))
                seen.insert(i, key)
                i += 1

    return MembershipDiff(ops)