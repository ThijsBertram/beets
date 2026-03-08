from __future__ import annotations

from typing import Optional

from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

from beetsplug.muziekmachine.services.ingestion import (
    pull_playlists_batch,
    pull_source_batch,
)
from beetsplug.muziekmachine.services.playlist_ingestion import resolve_playlist_selectors
from beetsplug.muziekmachine.sources.beets.mm_beets import BeetsBeetsPlugin
from beetsplug.muziekmachine.sources.spotify.mm_spotify import SpotifyBeetsPlugin
from beetsplug.muziekmachine.sources.spotify.playlist_adapter import SpotifyPlaylistAdapter
from beetsplug.muziekmachine.sources.youtube.mm_youtube import YoutubeBeetsPlugin
from beetsplug.muziekmachine.sources.youtube.playlist_adapter import YouTubePlaylistAdapter


class MuziekMachine(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.config.add({"playlist_patterns": []})

        self.pull_playlists = Subcommand(
            "mm-pull-playlists",
            help="Pull playlists from selected source(s) into in-memory objects",
        )
        self._add_common_pull_options(self.pull_playlists)
        self.pull_playlists.func = self._cmd_pull_playlists

        self.pull_songs = Subcommand(
            "mm-pull-songs",
            help="Pull songs from selected source(s) into in-memory objects",
        )
        self._add_common_pull_options(self.pull_songs)
        self.pull_songs.func = self._cmd_pull_songs

        self.spotify = SpotifyBeetsPlugin()
        self.beets = BeetsBeetsPlugin()
        self.youtube = YoutubeBeetsPlugin()

    def commands(self):
        return [self.pull_playlists, self.pull_songs]

    def _add_common_pull_options(self, cmd: Subcommand) -> None:
        cmd.parser.add_option(
            "--platform",
            dest="platform",
            default="all",
            choices=["all", "spotify", "youtube", "beets"],
            help="Source(s) to pull from",
        )
        cmd.parser.add_option(
            "--playlist",
            dest="playlist",
            default=None,
            help="Comma-separated playlist selector(s): id, exact name, or partial name",
        )
        cmd.parser.add_option(
            "--limit",
            dest="limit",
            type="int",
            default=None,
            help="Optional max mapped songs/playlists per source",
        )

    def _parse_cli_playlists(self, playlist_arg: Optional[str]) -> list[str]:
        if not playlist_arg:
            return []
        return [entry.strip() for entry in playlist_arg.split(",") if entry.strip()]

    def _default_playlist_selectors(self) -> list[str]:
        configured = self.config["playlist_patterns"].get()
        if isinstance(configured, str):
            configured = [configured]
        return [str(entry).strip() for entry in (configured or []) if str(entry).strip()]

    def _resolve_selectors(self, playlist_arg: Optional[str]) -> list[str]:
        explicit = self._parse_cli_playlists(playlist_arg)
        defaults = self._default_playlist_selectors()
        return resolve_playlist_selectors(explicit, defaults)

    def _resolve_platforms(self, platform: str) -> list[str]:
        if platform == "all":
            return ["spotify", "youtube", "beets"]
        return [platform]

    def _make_song_source(self, source: str, lib):
        if source == "spotify":
            return self.spotify._make_client_adapter()
        if source == "youtube":
            return self.youtube._make_client_adapter()
        if source == "beets":
            return self.beets._make_client_adapter(lib)
        raise ValueError(f"Unsupported source: {source}")

    def _cmd_pull_songs(self, lib, opts, args):
        selectors = self._resolve_selectors(opts.playlist)
        sources = self._resolve_platforms(opts.platform)

        batches = []
        for source in sources:
            try:
                client, adapter = self._make_song_source(source, lib)
                with client:
                    batch = pull_source_batch(
                        client,
                        adapter,
                        selectors=selectors,
                        limit=opts.limit,
                    )
                self._log.info(
                    "[pull-songs:%s] playlists=%d seen=%d mapped=%d duplicates=%d mapping_failures=%d",
                    source,
                    batch.result.playlists_scanned,
                    batch.result.songs_seen,
                    batch.result.songs_mapped,
                    batch.result.duplicates_observed,
                    batch.result.mapping_failures,
                )
                batches.append(batch)
            except Exception as exc:
                self._log.error("[pull-songs:%s] failed: %s", source, exc)

        return batches

    def _cmd_pull_playlists(self, lib, opts, args):
        selectors = self._resolve_selectors(opts.playlist)
        sources = self._resolve_platforms(opts.platform)

        batches = []
        for source in sources:
            try:
                if source == "spotify":
                    client, _ = self.spotify._make_client_adapter()
                    playlist_adapter = SpotifyPlaylistAdapter()
                elif source == "youtube":
                    client, _ = self.youtube._make_client_adapter()
                    playlist_adapter = YouTubePlaylistAdapter()
                elif source == "beets":
                    client, _ = self.beets._make_client_adapter(lib)
                    from beetsplug.muziekmachine.sources.beets.playlist_adapter import BeetsPlaylistAdapter

                    playlist_adapter = BeetsPlaylistAdapter(client)
                else:
                    raise ValueError(f"Unsupported source: {source}")

                with client:
                    batch = pull_playlists_batch(
                        client,
                        playlist_adapter,
                        selectors=selectors,
                        include_items=False,
                        limit=opts.limit,
                    )
                self._log.info(
                    "[pull-playlists:%s] playlists=%d",
                    source,
                    batch.result.playlists_scanned,
                )
                batches.append(batch)
            except Exception as exc:
                self._log.error("[pull-playlists:%s] failed: %s", source, exc)

        return batches
