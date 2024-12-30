from abc import ABC, abstractmethod
from typing import Dict, List, Union
import logging
from beets.library import Library


VALID_PLATFORMS = ['spotify', 'youtube']
VALID_PLAYLIST_TYPES = ['mm', 'pl', 'sl', 'all']
MATCH_KEYS = ['title', 'main_artist', 'artists', 'genre', 'subgenre', 'remixer', 'remix_type']
QUERY_KEYS = ['title', 'main_artist', 'artists', 'genre', 'subgenre', 'remixer', 'remix_type']

class Platform(ABC):
    def __init__(self):
        # Platform-specific initialization
        self._log = logging.getLogger(self.__class__.__name__)
        self.api = None
        self.pl_to_skip = self.config['pl_to_skip'].get()
        self.valid_pl_prefix = self.config['valid_pl_prefix'].get()

        self._log.info(f"Initializing {self.__class__.__name__} plugin.")
        self._log.info(f"Initalized with settings\npl_to_skip: {self.pl_to_skip}\nvalid_pl_prefix: {self.valid_pl_prefix}")
        
    @abstractmethod
    def initialize_api(self):
        """Initialize and return the platform-specific API client."""
        pass

    @abstractmethod
    def cleanup(self):
        """Cleanup resources like API clients or sessions."""
        pass

    @abstractmethod
    def _get_all_playlists(self) -> List[Dict[str, Union[str, int, float]]]:
        """Fetch all playlists for the platform."""
        pass

    @abstractmethod
    def _get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Union[str, int, float]]]:
        """Fetch all tracks from a given playlist."""
        pass

    @abstractmethod
    def _parse_track_item(self, lib: Library, item: Dict) -> Dict:
        """Parse individual track data into a standardized format."""
        pass
