# adapters/playlist_base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping, Optional
from beetsplug.muziekmachine.domain.models import PlaylistData, PlaylistRef
from beetsplug.muziekmachine.domain.playlist_diffs import compute_field_diff, compute_membership_diff, FieldDiff, MembershipDiff

class PlaylistAdapter(ABC):
    source: str


    @abstractmethod
    def collection_id(self, raw_playlist: Dict[str, Any]) -> str:
        return
    
    @abstractmethod
    def collection_name(self, raw_playlist: Dict[str, Any]) -> str:
        return

    @abstractmethod
    def make_ref(self, raw_playlist: Any) -> PlaylistRef:
        return
    
    @abstractmethod
    def render_current_fields(self, raw_playlist: Any) -> Mapping[str, Any]:
        return
    

    @abstractmethod
    def render_desired_fields(self, pd: PlaylistData) -> Mapping[str, Any]:
        return
    
    @abstractmethod
    def render_current_members(self, raw_playlist_items: List[Any]) -> List[str]: 
        return
    
    @abstractmethod
    def render_desired_members(self, pd: PlaylistData) -> List[str]:
        return
    
    @abstractmethod
    def field_capabilities(self) -> set[str]: 
        return
    
    @abstractmethod
    def membership_capabilities(self) -> set[str]:  # e.g., {'add','remove','move'}
        return

    # helpers
    def compute_field_diff(self, raw_playlist: Any, desired: PlaylistData) -> FieldDiff:
        current = self.render_current_fields(raw_playlist)
        desired_map = self.render_desired_fields(desired)
        # filter by capabilities
        filtered = {k: desired_map[k] for k in desired_map if k in self.field_capabilities()}
        return compute_field_diff(current, filtered)

    def compute_membership_diff(self, raw_playlist_items: List[Any], desired: PlaylistData) -> MembershipDiff:
        current_keys = self.render_current_members(raw_playlist_items)
        desired_keys = self.render_desired_members(desired)
        return compute_membership_diff(current_keys, desired_keys)
