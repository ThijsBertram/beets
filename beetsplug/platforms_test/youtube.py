from beets.plugins import BeetsPlugin
from contextlib import contextmanager
from beetsplug.platforms_test.platform import Platform
# Varia
import logging
from typing import List, Dict
import re
import requests


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
    
    def _parse_track_item(self, item) -> Dict:
        song_data = dict()

        # get title
        title = item['title']
        # fix title if artist is hidden in the topic 
        if ' - Topic' in item['channel']:
            a = item['channel'].split('- Topic')[0].strip()
            title = a + ' - ' + title
        # PARSE USING SIMPLE PARSER
        song_data = self.titleparser.extract_simple_ss(title)
        if not song_data:
            return None
        # # ELSE USE CHAPPIE OVERLORD
        # if not song_data:
        #     try:
        #         title, song_data = self.titleparser.send_gpt_request(args=[title])[0]
        #         song_data.pop('confidence')
        #     except IndexError:
        #         return song_data

        # ARTISTS
        artists = song_data.pop('artists')
        # if song_data['feat_artist']:
        #     artists += [song_data['feat_artist']]
        # if song_data['remixer']:
        #     artists += song_data['remixer']
        # remove duplicates and substrings
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