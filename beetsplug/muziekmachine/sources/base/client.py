from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from beetsplug.muziekmachine.domain.diffs import Diff
from beetsplug.muziekmachine.domain.models import CollectionStub, SourceRef
from beetsplug.muziekmachine.sources.base.errors import ClientCapabilityError


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_initial_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    jitter: bool = True


class SourceClient(AbstractContextManager, ABC):
    source: str
    retry_policy: RetryPolicy

    def __init__(self, retry_policy: Optional[RetryPolicy] = None) -> None:
        self.retry_policy = retry_policy or RetryPolicy()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self.close()
        finally:
            return False

    def supports_global_items(self) -> bool:
        return False

    # ----------------------------
    # Lifecycle / session handling
    # ----------------------------

    @abstractmethod
    def connect(self) -> None:
        return

    @abstractmethod
    def close(self) -> None:
        return

    @abstractmethod
    def capabilities(self) -> set[str]:
        """Supported writable song fields for `apply` (empty set => read-only song metadata)."""
        return

    def healthcheck(self) -> bool:
        return

    # ----------------------
    # Collections & items
    # ----------------------

    @abstractmethod
    def iter_collections(self) -> Iterable[CollectionStub]:
        return

    @abstractmethod
    def iter_items(self, collection: CollectionStub | None = None) -> Iterable[Any]:
        return

    @abstractmethod
    def get_item(self) -> Mapping[str, Any]:
        return

    @abstractmethod
    def iter_items_in_collection(self, coll) -> Iterable[Any]:
        return

    def iter_items_global(self) -> Iterable[Any]:
        for coll in self.iter_collections():
            yield from self.iter_items_in_collection(coll)

    # ----------------------
    # Optional playlist/source methods (formalized contract)
    # ----------------------

    def find_collections(self, query: str) -> Iterable[CollectionStub]:
        q = (query or "").strip().lower()
        for coll in self.iter_collections():
            if q in (coll.name or "").lower() or q == (coll.id or ""):
                yield coll

    def search_song_candidates(self, songdata: Any, limit: int = 10) -> Iterable[Mapping[str, Any]]:
        raise ClientCapabilityError(f"{self.source}: song search is not supported")

    def create_collection(self, name: str, description: str = "", public: bool = False) -> CollectionStub:
        raise ClientCapabilityError(f"{self.source}: playlist creation is not supported")

    def sync_collection_members(self, playlist_id: str, desired_external_ids: list[str]) -> None:
        raise ClientCapabilityError(f"{self.source}: playlist membership sync is not supported")

    def delete_collection(self, playlist_id: str) -> None:
        raise ClientCapabilityError(f"{self.source}: playlist deletion is not supported")

    # ---------------
    # Write / apply
    # ---------------

    @abstractmethod
    def apply(
        self,
        ref: SourceRef,
        diff: Diff,
        **kwargs,
    ) -> None:
        return
