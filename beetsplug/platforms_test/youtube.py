from beets.plugins import BeetsPlugin
from contextlib import contextmanager
from beetsplug.platforms_test.platform import Platform, MATCH_KEYS, QUERY_KEYS
# Varia
import logging
from typing import List, Dict
import re
import requests
from beetsplug.models.songdata import SongData
from fuzzywuzzy import fuzz

# YT
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import google_auth_oauthlib
import googleapiclient.discovery
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
# SC

# Beets
from beets.plugins import BeetsPlugin
from beets import config
import beetsplug.ssp as ssp
# Varia
import logging
from typing import List, Dict, Union
import os
from json.decoder import JSONDecodeError
import json

from contextlib import contextmanager


@contextmanager
def youtube_plugin():
    plugin = YoutubePlugin()
    try:
        yield plugin
    finally:
        plugin.cleanup()


class YoutubePlugin(BeetsPlugin):
    def __init__(self):
        BeetsPlugin.__init__(self)
        Platform.__init__(self) 

        self._log = logging.getLogger('beets.SpotifyPlugin')
        self._pm_log = logging.getLogger('beets.PlatformManager')

        self.api = self.authenticate()
        # init api
        self.api = self.initialize_youtube_api()
        # init SSP
        self.titleparser = ssp.SongStringParser()
        return
    
    def authenticate(self):
        # create directory to save credentials if it does not exits    
        auth_path = os.path.join(os.curdir, 'auth')

        if not os.path.isdir(auth_path):
            os.mkdir(auth_path)

        # OAUTH
        credentials = None
        # check if stored credentials are still valid
        scopes = self.config['scopes'].get()
        secrets_file = self.config['secrets_file'].get()
        try:
            credentials = Credentials.from_authorized_user_file(auth_path + '/yt_credentials.json', [scopes])
            credentials.refresh(Request())
        # crete new credentials if old expired
        except (RefreshError, JSONDecodeError) as error:
            credentials = None
            secrets_file = os.path.join(os.curdir, 'auth\\' + secrets_file)
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(secrets_file, [scopes])
            credentials = flow.run_local_server()

            cred_file = {"token": credentials.token,
                         "refresh_token": credentials.refresh_token,
                         "token_uri": credentials.token_uri,
                         "client_id": credentials.client_id,
                         "client_secret": credentials.client_secret,
                         "scopes": credentials.scopes}

            # sand store them in json
            with open(auth_path + '/yt_credentials.json', 'w') as token:
                token.write(json.dumps(cred_file))
        
        self.credentials = credentials
        return 

    def initialize_youtube_api(self):
        
        api_name = self.config['api_name'].get()
        api_version = self.config['api_version'].get()

        api_object = googleapiclient.discovery.build(api_name, api_version, credentials=self.credentials)
        return api_object
    
    def cleanup(self):
        try:
            self.api = None
            self._log.debug("Youtube API client dereferenced")
        except Exception as e:
            self._log.error(f"Error during Spotify API cleanup: {e}")
     
    def _get_all_playlists(self):

        playlists = []
        request = self.api.playlists().list(
            part='id,snippet,contentDetails',
            mine=True,
            maxResults=50
        )

        while request:
            try:
                response = request.execute()
                playlists.extend(response['items'])
                request = self.api.playlists().list_next(request, response)
            except HttpError as e:
                print(f"An HTTP error {e.resp.status} occurred: {e.content}")
                break
        
        playlists = [{'playlist_id': playlist['id'],
                      'playlist_name': playlist['snippet']['title'],
                      'playlist_description': playlist['snippet']['description']} for playlist in playlists]

        return playlists
    
    def _get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Union[str, int, float]]]:

        videos = []
        request = self.api.playlistItems().list(
            part='contentDetails,snippet',
            playlistId=playlist_id,
            maxResults=50
        )

        while request:
            try:
                response = request.execute()
                videos.extend(response['items'])
                request = self.api.playlistItems().list_next(request, response)
            except HttpError as e:
                print(f"An HTTP error {e.resp.status} occurred: {e.content}")
                break

        items = []
        for video in videos:
            track_info = {'id': video['id'],
                    'title': video['snippet']['title'],
                    'description': video['snippet']['description'],
                    'youtube_id': video['contentDetails']['videoId']}
    
            try:
                track_info['channel'] = video['snippet']['videoOwnerChannelTitle']
            except KeyError:
                self._log.warning(f"{video['snippet']['title']} in playlist: {playlist_id}")
                continue

            items.append(track_info)

        tracks = {'items': items}
        return tracks
    
    def _parse_track_item(self, lib, item) -> Dict:

        song_data = dict()

        # get title
        title = item['title']
        # fix title if artist is hidden in the topic 
        if ' - Topic' in item['channel']:
            a = item['channel'].split('- Topic')[0].strip()
            title = a + ' - ' + title
        # PARSE USING SIMPLE PARSER
        song_data = self.titleparser.extract_simple_ss(title)

        q = f"youtube_id:{item['youtube_id']}"
        song_exists = lib.items(q).get()

        if song_exists:
            song_data = SongData(**dict(song_exists)).model_dump()
            self._pm_log.info(f"{song_data['main_artist']} - {song_data['title']} \033[38;5;220malready exists\033[0m in the library.")
            return song_data

        # ELSE USE CHAPPIE OVERLORD
        if not song_data:
            try:
                title, song_data = self.titleparser.send_gpt_request(args=[title])[0]
                song_data.pop('confidence')
            except IndexError as e:
                self._log.error(f"ERROR parsing {title}: {e}")
                return song_data

        # ARTISTS
        artists = song_data.pop('artists')
        # if song_data['feat_artist']:
        #     artists += [song_data['feat_artist']]
        # if song_data['remixer']:
        #     artists += song_data['remixer']
        # remove duplicates and substrings
        if not artists:
            self._pm_log.error("The 'artists' list is empty before deduplication.")
            return dict()
        # Remove duplicates based on substrings
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = [a for a in artists if a not in substrings]
        main_artist = artists[0]
        # sort
        artists = sorted(artists)

        # populate dict 
        song_data['youtube_id'] = item['youtube_id']
        song_data['artists'] = artists
        song_data['main_artist'] = main_artist



        return song_data
    


    def search_track_youtube(self, 
                             track: Dict[str, str], 
                             query_keys: List[str] = QUERY_KEYS) -> List[Dict[str, str]]:
        """
        Search for a track on YouTube using metadata. If no matches are found with all query keys,
        retry with a simplified query using only 'artist' and 'title'.

        Args:
            track (Dict[str, str]): A dictionary containing track metadata.
            query_keys (List[str]): A list of keys to use for constructing the query.

        Returns:
            List[Dict[str, str]]: List of search result items from YouTube API.
        """
        try:
            query_parts = [track[key] for key in query_keys if track.get(key)]
            query = " ".join(query_parts)

            # Perform search on YouTube
            search_response = self.api.search().list(
                q=query,
                type="video",
                part="id,snippet",
                maxResults=10
            ).execute()

            search_results = search_response.get("items", [])

            # If no results, retry with simplified query
            if not search_results:
                self._log.warning("No results found with full query, retrying with simplified query.")
                query = f"{track['artist']} {track['title']}"
                search_response = self.api.search().list(
                    q=query,
                    type="video",
                    part="id,snippet",
                    maxResults=10
                ).execute()
                search_results = search_response.get("items", [])

            return search_results
        except Exception as e:
            self._log.error(f"Error searching for track with metadata {track}: {e}")
            return []

    def match_results_youtube(self, 
                              track: Dict[str, str], 
                              search_results: List[Dict[str, str]], 
                              match_keys: List[str] = MATCH_KEYS, 
                              fuzz_threshold: int = 90) -> str:
        """
        Match a track with search results based on metadata using fuzzy matching.

        Args:
            track (Dict[str, str]): A dictionary containing track metadata.
            search_results (List[Dict[str, str]]): List of search result items from YouTube API.
            match_keys (List[str]): A list of keys to use for matching results.
            fuzz_threshold (int): Minimum fuzzy match score for a key/value pair to be considered a match.

        Returns:
            str: YouTube video ID if a match is found, None otherwise.
        """
        for item in search_results:
            item_metadata = {
                "title": item["snippet"]["title"].lower(),
                "channel": item["snippet"].get("channelTitle", "").lower(),
            }

            if all(
                fuzz.partial_ratio(track.get(key, "").lower(), item_metadata.get(key, "")) >= fuzz_threshold
                for key in match_keys if track.get(key)
            ):
                return item["id"]["videoId"]
        return None

    def add_songs_to_playlist_youtube(self, 
                                      playlist_id: str, 
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
