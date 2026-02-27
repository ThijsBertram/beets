from __future__ import annotations
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.youtube.client import YouTubeClient
from beetsplug.muziekmachine.sources.youtube.adapter import YouTubeAdapter
from beetsplug.muziekmachine.sources.youtube.mapper import YouTubeMapper
from beetsplug.muziekmachine.services.ingestion import pull_source
from beetsplug.muziekmachine.services.playlist_ingestion import iter_collection_stubs, iter_playlist_data
from beetsplug.muziekmachine.sources.youtube.playlist_adapter import YouTubePlaylistAdapter

class YoutubeBeetsPlugin(BeetsPlugin):
    """Registers CLI to pull YouTube data via the new client/adapter/mapper."""
    name = "mm_youtube"

    def __init__(self):
        super().__init__()
        # Config keys expected under this plugin name in beets config:
        #   client_secrets_file, token_path, scopes (optional)
        self.pull_songs = Subcommand('yt-pull-songs', help='Pull YouTube playlists and map to SongData')
        self.pull_songs.parser.add_option('--playlist', dest='playlist', help='Playlist name or id (optional)')
        self.pull_songs.func = self._cmd_pull_songs

        self.pull_playlists = Subcommand('yt-pull-playlist')
        self.pull_playlists.parser.add_option('--playlist', dest='playlist')
        self.pull_playlists.func = self._cmd_pull_playlists

    def commands(self):
        return [self.pull_songs, self.pull_playlists]

    def _make_client_adapter(self):
        client = YouTubeClient(
            client_secrets_file=self.config['client_secrets_file'].get(),
            token_path=self.config['token_path'].get() or 'auth/yt_credentials.json',
            scopes=self.config['scopes'].get(),
        )
        adapter = YouTubeAdapter(client=client, mapper=YouTubeMapper())
        return client, adapter

    def _cmd_pull_songs(self, lib, opts, args):
        # If no specific playlist provided, iterate all user playlists
        if opts.playlist:
            selectors = [pl.strip() for pl in opts.playlist.split(',')]
        else:
            client, _ = self._make_client_adapter()
            with client:
                selectors = [stub.name for stub in iter_collection_stubs(client)]

        client, adapter = self._make_client_adapter()
        with client:
            count = 0
            for sd, ref in pull_source(client, adapter, playlist=selectors):
                self._log.info(f"[YouTube] {sd.main_artist or ''} — {sd.title} (id={sd.youtube_id})")
                count += 1
            self._log.info(f"Pulled {count} YouTube tracks.")

    # ================
    # PULL PLAYLISTS
    # ================

    def _cmd_pull_playlists(self, lib, opts, args):

        if opts.playlist:
            playlists = [pl.strip() for pl in opts.playlist.split(',')]
        else:
            client, adapter = self._make_client_adapter()

            with client:
                playlists = client.iter_collections()
                playlists = [pl.name for pl in playlists]

        self._pull_playlists(playlists)   

        return
    
    def _pull_playlists(self, playlists):
        client, adapter = self._make_client_adapter()

        playlist_adapter = YouTubePlaylistAdapter()
        
        with client:
            count = 0 
            for pd in iter_playlist_data(client, playlist_adapter, selectors=playlists, include_items=False):
                self._log.info(f"[Spotify] Playlist data pulled for playlist {pd.name}")
                count += 1 
        self._log.info(f"Pulled {count} Spotify playlists.")
        return