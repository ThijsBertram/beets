from beets.plugins import BeetsPlugin
from contextlib import contextmanager
from beetsplug.platforms_test.platform import Platform

# SF
import spotipy
from spotipy.oauth2 import SpotifyOAuth
# Beets
from beets.plugins import BeetsPlugin
from beets import config

# Varia
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
     
    
    
    
    
    
    
    
    
    def _parse_track_item(self, item) -> Dict:
        song_data = dict()
        track = item['track']
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

        return song_data
    
    def _get_playlist_tracks(self, playlist_id):
        tracks = self.api.playlist_tracks(playlist_id)
        return tracks
    
   