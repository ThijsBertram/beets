from beets.plugins import BeetsPlugin
from contextlib import contextmanager
from beetsplug.platforms_test.platform import Platform, QUERY_KEYS, MATCH_KEYS
from beetsplug.models.songdata import SongData
import urllib.parse
# SF
import spotipy
from spotipy.oauth2 import SpotifyOAuth
# Beets
from beets.plugins import BeetsPlugin
from beets import config

# Varia
from fuzzywuzzy import fuzz

import logging
from typing import List, Dict
import re
import requests


@contextmanager
def spotify_plugin():
    plugin = SpotifyPlugin()
    try:
        yield plugin
    finally:
        plugin.cleanup()


class SpotifyPlugin(BeetsPlugin, Platform):
    def __init__(self):
        BeetsPlugin.__init__(self)
        Platform.__init__(self) 

        self._log = logging.getLogger('beets.SpotifyPlugin')
        self.session = requests.Session()
        self.api = self.initialize_api()
        return
    
    def initialize_api(self):
        return spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id = self.config['client_id'].get(),
            client_secret = self.config['client_secret'].get(),
            redirect_uri = self.config['redirect_uri'].get(),
            scope="playlist-read-private playlist-modify-private playlist-modify-public",
            requests_session = self.session
        ))
    
    def cleanup(self):
        """Explicitly close the requests session."""
        try:
            if self.session:
                self.session.close()  # Close the session to clean up resources
                self._log.debug("Spotify session closed.")
        except Exception as e:
            self._log.error(f"Error during cleanup: {e}")

        try:
            self.api = None
            self._log.debug("Spotify API client dereferenced.")
        except Exception as e:
            self._log.error(f"Error during Spotify API cleanup: {e}")
    
    def _get_all_playlists(self) -> List[Dict[str, str]]:
        playlists = []
        offset = 0
        limit = 50
        while True:
            results = self.api.current_user_playlists(limit=limit, offset=offset)
            playlists.extend(results['items'])
            if results['next'] is None:
                break
            offset += limit

        return [{'playlist_name': p['name'], 
                 'playlist_id': p['id'],
                 'playlist_description': p['description']} for p in playlists]
         
    def _get_playlist_tracks(self, playlist_id):
        tracks = self.api.playlist_tracks(playlist_id)
        return tracks['items']
    
    def _parse_song_item(self, lib, track, search_results=False) -> Dict:
        song_data = dict()
        if not search_results:
            track = track['track']

        # title
        title = track['name'].split(' - ')[0]

        # ARTISTS
        artists = [artist['name'] for artist in track['artists']]

        # main 
        main_artist = artists[0]
        # feat 
        _ = re.search(r'\(feat\. (.*?)\)', title)
        feat_artist, title = (_.group(1).strip(), title[:_.start()] + title[_.end():].strip()) if _ else ('', title)
        # if feat_artist:
        #     artists += [feat_artist]
        # # remix 
        remixer = track['name'].split(' - ')[1].replace(' Remix', '') if len(track['name'].split(' - ')) > 1 else ''
        # if remixer:
        #     artists += [remixer]
        # remove duplicates and substrings
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = [a for a in artists if a not in substrings]
        # sort
        artists = sorted(artists)
        # Filter out strings that are substrings of any other string
        # spotify id
        spotify_id = track['id']
        # populate dict
        song_data['artists'] = artists
        song_data['title'] = title
        song_data['remixer'] = remixer
        song_data['remix_type'] = 'Remix' if remixer else ''
        song_data['spotify_id'] = spotify_id
        song_data['feat_artist'] = feat_artist
        song_data['main_artist'] = main_artist
        song_data = SongData(**dict(song_data))
        return song_data

    def _create_playlist(self, playlist_name):
        existing_playlists = self._get_all_playlists()

        playlist_id = next(
            (p["playlist_id"] for p in existing_playlists if p["playlist_name"].lower() == playlist_name.lower()),
            None
        )

        # Step 3: Create if not found
        if not playlist_id:
            self._log('debug', f'PLAYLIST {playlist_name} created (did not exist yet)')
            new_playlist = self.api.user_playlist_create(
                user=self.api.me()['id'],
                name=playlist_name,
                public=False,
                description=""
            )
            playlist_id = new_playlist["id"]

        return playlist_id
    
    def _search_song(self,
                     lib,
                     song: SongData) -> List:
        
        query = f"track:'{song.title}' artist:'{' '.join(song.artists)}'"

        try:
            
            results = self.api.search(q=query, type="track", limit=5, market="US", offset=0)['tracks']['items']
            results = [dict(result) for result in results]

            if not results:
                return None
            
            return results 

        except Exception as e:
            self._log.log("error", f"Error searching Spotify for track: {e}")
            return None
        
    def _parse_search_results(self, lib, results):
        songs = [self._parse_song_item(lib, result, search_results=True) for result in results]

        return songs
    
    def match_results(self, 
                      track: Dict[str, str], 
                      search_results: List[Dict[str, str]], 
                      match_keys: List[str] = MATCH_KEYS, 
                      fuzz_threshold: int = 90) -> str:
        """
        Match a track with search results based on metadata using fuzzy matching.

        Args:
            track (Dict[str, str]): A dictionary containing track metadata.
            search_results (List[Dict[str, str]]): List of search result items from Spotify API.
            match_keys (List[str]): A list of keys to use for matching results.
            fuzz_threshold (int): Minimum fuzzy match score for a key/value pair to be considered a match.

        Returns:
            str: Spotify track ID if a match is found, None otherwise.
        """
        for item in search_results:
            item_metadata = {
                "artist": [artist['name'] for artist in item['artists']],
                "title": item['name'].split(' - ')[0].lower(),
                "full_title": item['name'].lower(),
            }

            if all(
                (key == "artist" and any(
                    fuzz.ratio(track[key].lower(), artist.lower()) >= fuzz_threshold
                    for artist in item_metadata[key]
                )) or
                (key != "artist" and fuzz.partial_ratio(track.get(key, "").lower(), item_metadata.get(key, "")) >= fuzz_threshold)
                for key in match_keys if track.get(key)
            ):
                return item['id']
        return None

    def _add_song_to_playlist(self, song, playlist_id):

        self.api.playlist_add_items(playlist_id, [song.spotify_id])
        return True