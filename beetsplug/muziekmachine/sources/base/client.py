from __future__ import annotations
from abc import ABC, abstractmethod
from contextlib import contextmanager, AbstractContextManager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, Optional, Tuple, Mapping

from beetsplug.muziekmachine.domain.diffs import Diff
from beetsplug.muziekmachine.domain.models import SourceRef, CollectionStub

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_initial_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    jitter: bool = True



class SourceClient(AbstractContextManager, ABC):
    source: str
    retry_policy: RetryPolicy

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None
    ) -> None:
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
        """
        Declare supported write fields (e.g., {"title","comment"}) or empty set for read-only sources.
        Services will filter diffs with this.
        """
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

    # ---------------
    # Write / apply
    # ---------------

    @abstractmethod
    def apply(
        self,
        ref: SourceRef,
        diff: Diff,
        **kwargs
    ) -> None:
        
        return
    
    