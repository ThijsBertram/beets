from beets.plugins import BeetsPlugin
from contextlib import contextmanager
from beetsplug.platforms_test.platform import Platform, QUERY_KEYS, MATCH_KEYS

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
     
    
    
    
    
    
    
    
    
    def _parse_track_item(self, lib, item) -> Dict:
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
    
   




    def search_track(self, 
                     track: Dict[str, str], 
                     query_keys: List[str] = QUERY_KEYS) -> List[Dict[str, str]]:
        """
        Search for a track on Spotify using metadata. If no matches are found with all query keys,
        retry with a simplified query using only 'artist' and 'title'.

        Args:
            track (Dict[str, str]): A dictionary containing track metadata.
            query_keys (List[str]): A list of keys to use for constructing the query.

        Returns:
            List[Dict[str, str]]: List of search result items from Spotify API.
        """
        try:
            query_parts = [f"{key}:{track[key]}" for key in query_keys if track.get(key)]
            query = " ".join(query_parts)

            # Perform search on Spotify
            search_results = self.api.search(q=query, type='track', limit=10)

            # If no results, retry with simplified query
            if not search_results['tracks']['items']:
                self._log.warning("No results found with full query, retrying with simplified query.")
                query = f"artist:{track['artist']} track:{track['title']}"
                search_results = self.api.search(q=query, type='track', limit=10)

            return search_results['tracks']['items']
        except Exception as e:
            self._log.error(f"Error searching for track with metadata {track}: {e}")
            return []

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

    def add_songs_to_playlist_youtube(self, playlist_id: str, 
                                      tracks: List[Dict[str, str]], 
                                      query_keys: List[str] = QUERY_KEYS, 
                                      match_keys: List[str] = MATCH_KEYS, 
                                      fuzz_threshold: int = 90) -> Dict:
        """
        Add songs to a YouTube playlist and return information about newly found IDs and playlist-item relationships.

        Args:
            playlist_id (str): The ID of the YouTube playlist.
            tracks (List[Dict[str, str]]): A list of dictionaries containing track metadata.
            query_keys (List[str]): A list of keys to use for constructing the search query.
            match_keys (List[str]): A list of keys to use for matching search results.
            fuzz_threshold (int): Minimum fuzzy match score for matching key/value pairs.

        Returns:
            Dict: A dictionary containing:
                - 'new_platform_ids': List of tuples (song_id, youtube_id).
                - 'playlist_items': List of tuples (playlist_id, song_id).
        """
        track_ids = []
        total_tracks = len(tracks)
        not_found_count = 0

        self._log.info(f"Adding {total_tracks} songs to playlist {playlist_id} on YouTube.")

        new_platform_ids = []
        playlist_items = []

        for track in tracks:
            song_id = track.get("song_id")  # Assuming the parent class provides 'song_id'
            search_results = self.search_track_youtube(track, query_keys)
            matched_track_id = self.match_results_youtube(track, search_results, match_keys, fuzz_threshold=fuzz_threshold)

            if matched_track_id:
                track_ids.append(matched_track_id)
                self._log.info(f"Matched track: {track['title']} by {track['artist']}")

                # Collect new platform ID
                if song_id:
                    new_platform_ids.append((song_id, matched_track_id))
                # Collect playlist-item relationship
                playlist_items.append((playlist_id, song_id))
            else:
                self._log.warning(f"No match found for track: {track['title']} by {track['artist']}")
                not_found_count += 1

        if not track_ids:
            self._log.warning("No valid track IDs to add to the playlist.")
            return {"new_platform_ids": new_platform_ids, "playlist_items": playlist_items}

        for track_id in track_ids:
            try:
                self.api.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": track_id,
                            }
                        }
                    }
                ).execute()
                self._log.info(f"Added track with ID {track_id} to playlist {playlist_id}.")
            except Exception as e:
                self._log.error(f"Failed to add track with ID {track_id} to playlist {playlist_id}: {e}")

        self._log.info(f"Successfully added {len(track_ids)}/{total_tracks} tracks to playlist {playlist_id}.")
        if not_found_count > 0:
            self._log.info(f"{not_found_count}/{total_tracks} tracks could not be found.")

        return {"new_platform_ids": new_platform_ids, "playlist_items": playlist_items}
