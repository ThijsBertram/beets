# adapters/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Dict

from beetsplug.muziekmachine.sources.base.mapper import Mapper
from beetsplug.muziekmachine.domain.diffs import Diff, compute as compute_diff
from beetsplug.muziekmachine.domain.models import SourceRef  # tiny pointer to a record in a source



class AdapterError(Exception):
    """Base for adapter-level errors."""


class MappingError(AdapterError):
    """Raised when raw -> SongData (or SongData -> raw projection) fails."""


class CapabilityError(AdapterError):
    """Raised when an adapter is asked to project or update a field it doesn't support."""



class SourceAdapter(ABC):
    """
    Bridges a source client (I/O) and canonical SongData semantics.
    Responsibilities:
      - Normalize raw -> SongData       (via a Mapper)
      - Project SongData -> source dict (for diffing/writing)
      - Declare write capabilities
      - Derive a SourceRef from raw
      - Provide convenience helpers to compute diffs and fetch current state
    """

    source: str  # e.g. "spotify", "rekordbox", "beets", "filesystem"

    def __init__(self, client: Any, mapper: Mapper) -> None:
        self.client = client
        self.mapper = mapper

    # ---------- conversions ----------
    def to_songdata(self, raw: Any) -> Any:
        """
        Raw source object -> SongData (delegates to mapper).
        """
        try:
            return self.mapper.to_songdata(raw)
        except Exception as e:
            print(dict(raw))
            raise MappingError(f"{self.source}: failed to map raw -> SongData for raw info:\n{raw}") from e

    @abstractmethod
    def render_desired(self, songdata: Any, ref: Optional[SourceRef] = None) -> Mapping[str, Any]:
        """
        SongData -> source-native dict **minimal projection** used for diffing/writing.
        Only include fields this source can represent. Keep it shallow (flat dict).
        """
        raise NotImplementedError

    @abstractmethod
    def render_current(self, raw: Any) -> Mapping[str, Any]:
        """
        Raw -> source-native dict **minimal projection** used for diffing/writing.
        Mirrors render_desired() in shape so Diff.compute() works field-by-field.
        """
        raise NotImplementedError

    # ---------- identity ----------
    @abstractmethod
    def make_ref(self, raw: Any, extra_keys: Optional[Dict[str, Any]] = None) -> SourceRef:
        """
        Produce a stable pointer to this raw record so services can re-fetch/patch later.
        """
        raise NotImplementedError

    # ---------- capabilities ----------
    @abstractmethod
    def capabilities(self) -> set[str]:
        """
        Which fields this source supports updating (e.g., {'title','comment'}).
        If empty, the source is effectively read-only for our purposes.
        """
        raise NotImplementedError

    # ---------- convenience helpers (compose with client) ----------
    def fetch_current(self, ref: SourceRef) -> Mapping[str, Any]:
        """
        Get the current **projection** for 'ref' (fetch raw, then render_current).
        """
        raw = self.client.get_item(ref)
        return self.render_current(raw)

    def compute_diff(self, songdata: Any, ref: SourceRef) -> Diff:
        """
        Compare current state in the source vs desired projection from SongData.
        """
        current = self.fetch_current(ref)
        desired = self.render_desired(songdata, ref)
        return compute_diff(current, desired).filter(self.capabilities())
