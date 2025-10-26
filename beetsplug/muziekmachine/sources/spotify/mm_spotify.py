from __future__ import annotations
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config

from beetsplug.muziekmachine.sources.spotify.client import SpotifyClient
from beetsplug.muziekmachine.sources.spotify.adapter import SpotifyAdapter
from beetsplug.muziekmachine.sources.spotify.mapper import SpotifyMapper
# from beetsplug.muziekmachine.services.ingestion import pull_source

from beetsplug.muziekmachine.services.ingestion import pull_source
from beetsplug.muziekmachine.services.playlist_ingestion import iter_collection_stubs, iter_playlist_data
from beetsplug.muziekmachine.sources.spotify.playlist_adapter import SpotifyPlaylistAdapter

class SpotifyBeetsPlugin(BeetsPlugin):
    """Registers a CLI command to pull Spotify data using the new client+adapter+mapper."""
    name = "mm_spotify"

    def __init__(self):
        super().__init__()

        self.pull_songs = Subcommand('sf-pull-songs', help='Pull Spotify playlists and map to SongData')
        self.pull_songs.parser.add_option('--playlist', dest='playlist', help='Playlist name or id to pull (optional)')
        self.pull_songs.func = self._cmd_pull_songs

        self.pull_playlists = Subcommand('sf-pull-playlist')
        self.pull_playlists.parser.add_option('--playlist', dest='playlist')
        self.pull_playlists.func = self._cmd_pull_playlists

        # self.client, self.adapter = self._make_client_adapter()


    def commands(self):
        return [self.pull_songs, self.pull_playlists]

    def _make_client_adapter(self):

        client = SpotifyClient(
            client_id=self.config['client_id'].get(),
            client_secret=self.config['client_secret'].get(),
            redirect_uri=self.config['redirect_uri'].get(),
        )
        adapter = SpotifyAdapter(client=client, mapper=SpotifyMapper())
        return client, adapter

    # ================
    # PULL SONGS
    # ================

    def _cmd_pull_songs(self, lib, opts, args):
        if opts.playlist:
                playlists = [pl.strip() for pl in opts.playlist.split(',')]
        else:
            client, adapter = self._make_client_adapter()

            with client:
                playlists = client.iter_collections()
                playlists = [pl.name for pl in playlists]
                
        self._pull_songs(playlists)
        return

    def _pull_songs(self, playlists):
        client, adapter = self._make_client_adapter()

        with client:
            count = 0
            for sd, ref in pull_source(client, adapter, playlist=playlists):
                # For now, just log a summary; later you’ll pass these into Matching/Merging/Sync.
                self._log.info(f"[Spotify] {sd.main_artist} — {sd.title} (id={sd.spotify_id})")
                count += 1
            self._log.info(f"Pulled {count} Spotify tracks.")

        return
    
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

        playlist_adapter = SpotifyPlaylistAdapter()
        
        with client:
            count = 0 
            for pd in iter_playlist_data(client, playlist_adapter, selectors=playlists, include_items=False):
                self._log.info(f"[Spotify] Playlist data pulled for playlist {pd.name}")
                count += 1 
        self._log.info(f"Pulled {count} Spotify playlists.")
        return