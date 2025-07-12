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
            maxResults=100
        )

        while request:
            try:
                response = request.execute()
                playlists.extend(response['items'])
                request = self.api.playlists().list_next(request, response)
            except HttpError as e:
                self._log.debug( f"An HTTP error {e.resp.status} occurred: {e.content}")
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
                self._log.debug(f"An HTTP error {e.resp.status} occurred: {e.content}")
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

        return items
      
    def _parse_song_item(self, lib, song) -> SongData:

        q = f"youtube_id:{song['youtube_id']}"
        song_exists = lib.items(q).get()

        if song_exists:
            song_data = SongData(**dict(song_exists))
        if song_exists:
            song_data = SongData(**dict(song_exists))
            self._pm_log.debug(f"{song_data.main_artist} - {song_data.title} \033[38;5;220malready exists\033[0m in the library.")
            return song_data

        song_data = dict()

        # get title
        title = song['title']
        # fix title if artist is hidden in the topic 
        if ' - Topic' in song['channel']:
            a = song['channel'].split('- Topic')[0].strip()
            title = a + ' - ' + title
        # PARSE USING SIMPLE PARSER
        song_data = self.titleparser.extract_simple_ss(title)

        # ELSE USE CHAPPIE OVERLORD
        if not song_data:
            try:
                title, song_data = self.titleparser.send_gpt_request(lib, args=[title])[0]
                try:
                    song_data.pop('confidence')
                except KeyError:
                    pass
            except IndexError as e:
                self._log.error(f"ERROR parsing {title}: {e}")
                return song_data

        # ARTISTS
        artists = song_data.pop('artists')
        if not artists:
            self._log.log("debug", "The 'artists' list is empty before deduplication.")
            return dict()
        # Remove duplicates based on substrings
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = [a for a in artists if a not in substrings]
        main_artist = artists[0]
        # sort
        artists = sorted(artists)

        # populate dict 
        song_data['youtube_id'] = song['youtube_id']
        song_data['artists'] = artists
        song_data['main_artist'] = main_artist

        song_data = SongData(**dict(song_data))

        return song_data

    def _create_playlist(self, playlist_name):
        existing_playlists = self._get_all_playlists()

        playlist_id = next(
            (p["playlist_id"] for p in existing_playlists if p["playlist_name"].lower() == playlist_name.lower()),
            None
        )

        if not playlist_id:
            self._log.debug(f'PLAYLIST {playlist_name} created (did not exist yet)')
            
            create_response = self.api.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": playlist_name,
                        "description": ""
                    },
                    "status": {
                        "privacyStatus": "private"
                    }
                }
            ).execute()
            playlist_id = create_response["id"]
        
        return playlist_id
  
    def _parse_search_results(self, lib, results):
        parsed_results = list()
        
        for result in results:
            youtube_id = result['id']['videoId']
            channel_name = result['snippet']['channelTitle']
            title = result['snippet']['title']

            result['youtube_id'] = youtube_id
            result['channel'] = channel_name
            result['title'] = title
            
            parsed_results.append(self._parse_song_item(lib, result))
        return parsed_results
    
    def _search_song(self, lib, song):
        query = f"{' '.join(song.artists)} - {song.title}"

        try:
            response = self.api.search().list(
                part="id,snippet",
                q=query,
                type="video",
                maxResults=5
            ).execute()

            results = response.get("items", [])

            if not results:
                return None

            return results
        except Exception as e:
            self._log.debug(f"Error searching YouTube for track: {e}")
            return None

    def _add_song_to_playlist(self, song, playlist_id):
        
        song_id = song.youtube_id
        try:
            self.api.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": song_id
                        }
                    }
                }            
            ).execute()
        except Exception as e:
            self._log.log("error", "UNABLE TO ADD DUE TO: ", e)
            return False
        return True
    