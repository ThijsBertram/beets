from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from beetsplug.custom_logger import CustomLogger
from beetsplug.ssp import SongStringParser

# Beets
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
from beets.dbcore.query import SubstringQuery, OrQuery, AndQuery, NoneQuery

import asyncio
from .download import Downloader
from .search import Searcher
from slskd_api import SlskdClient

import glob
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import shutil
from tenacity import retry, stop_after_attempt, wait_exponential

class SoulSeekPlugin(BeetsPlugin):
    """
    Redesigned SoulSeekPlugin to manage tasks and logging with controlled throttling.

    Refactored so the CLI subcommand is a thin wrapper around a core
    `download_songs()` method that can also be called from other code.
    """

    def __init__(self):
        super().__init__()

        # Initialize the custom logger
        self._log = CustomLogger("SoulSeekPlugin", default_color="cyan")

        # Configuration setup
        self.max_threads = int(self.config['max_threads'].get(1))
        self.dl_timeout = int(self.config['dl_timeout'].get(600))
        self.download_dir = self.config['slsk_dl_dir'].get()
        self.library_dir = os.path.abspath(config['directory'].get())
        self.host = self.config['host'].get()
        self.api_key = self.config['api_key'].get()

        # Semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(2)

        # Initialize downloader/searcher/client
        self.client = SlskdClient(api_key=self.api_key, host=self.host)
        self.downloader = Downloader(self.client, self._log, self.semaphore, timeout=self.dl_timeout)
        self.searcher = Searcher(self.client, self._log)
        self.ssp = SongStringParser()

        # Download queue & results
        self.download_queue = Queue()
        self.results = []

        # Define the Beets CLI subcommand
        self.dl_slsk = Subcommand('dl-slsk', help='Download songs from Soulseek.')
        self.dl_slsk.parser.add_option('--n-tries', dest='tries', default='3',
                                       help='Number of times to retry a download.')
        self.dl_slsk.parser.add_option('--genres', dest='genres', default='all',
                                       help='Comma-separated list of genres or "all".')
        # CLI entrypoint
        self.dl_slsk.func = self.cli_download

        # Optionally do a cleanup on initialization
        self.clean_up()

    def commands(self):
        """Register the subcommands this plugin provides."""
        return [self.dl_slsk]

    # ──────────────────────────────────────────────────────────────────────────
    #  CLI ENTRYPOINT (Thin Wrapper)
    # ──────────────────────────────────────────────────────────────────────────
    def cli_download(self, lib, opts, args):
        """
        CLI entrypoint for `beet dl-slsk`.
        - Parses CLI options for n_tries and genres.
        - Calls the main download logic (async) within `asyncio.run()`.
        """
        # Convert CLI opts to Python types
        n_tries = int(opts.tries)
        genres = opts.genres

        try:
            # Run the async method from a sync CLI context
            asyncio.run(self.download_songs(lib, n_tries, genres))
        except RuntimeError as e:
            self._log.log("error", f"Async runtime error occurred: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    #  CALLABLE FROM OTHER CODE (e.g. your pipeline)
    # ──────────────────────────────────────────────────────────────────────────
    async def download_songs(self, lib, n_tries=3, items=None):
        """
        The *core* method to download songs.

        Can be called from:
          1) The CLI subcommand (via cli_download).
          2) Your custom pipeline code, e.g.:
              await plugin.download_songs(lib, 5, 'rock')
        """

        # 2. Clear previous results
        self.results = []

        # 3. Process items, respecting the semaphore
        for item in items:
            async with self.semaphore:
                self._log.log("debug", f"Processing item: {item['title']}")
                # We'll do a backoff search + attempts
                try:
                    result = await self._process_task(item, n_tries)
                    self.results.append(result)
                    self._log.log("info", f"Task completed for item: {item['title']} -> {result['status']}")
                except Exception as e:
                    self._log.log("debug", f"Error occurred for item {item['title']}: {e}")

        return self.results
    # ──────────────────────────────────────────────────────────────────────────
    #  INTERNAL LOGIC
    # ──────────────────────────────────────────────────────────────────────────
    async def _process_task(self, item, n_tries):
        """
        Process a single item:
         - Search on Soulseek with retries/backoff
         - Match best results
         - Attempt to download
         - Move the downloaded file into the library
        """

        try:

            # 0. Record the attempt immediately
            item['last_download_attempt'] = datetime.now().isoformat()
            item.store()  # commit to DB
            # 1. Perform search
            self._log.log("debug", f"Starting search for item: {item['title']}")
            results = await self._search_with_backoff(item)
            if not results:
                self._log.log("debug", f"No search results for item: {item['title']}")
                return {'item': item, 'status': 'failed: no_results'}

            # 2. Match results to item
            matches = self.searcher.match_results(results, item)
            if not matches:
                self._log.log("debug", f"No matches found for item: {item['title']}")
                return {'item': item, 'status': 'failed: no_matches'}

            # 3. Attempt downloads on top matches
            for match in matches[:5]:
                self._log.log("debug", f"Download attempt for {match['file']['filename']}")
                file = await self.downloader.download(match['file'], match['username'])
                if not file:
                    self._log.log("warning", f"Download returned no file object. Trying next match...")
                    continue

                # Check if file was queued or errored
                if file['state'] in ['Queued, Remotely', 'Completed, Errored']:
                    self._log.log("debug", f"File queued or errored: {file['filename']}, continuing.")
                    continue

                # If we have a valid downloaded file, move it
                moved_path = self._move_downloaded_file(file, item)
                if moved_path:
                    item['path'] = moved_path
                    item.store()

                    self._log.log("debug", f"Download & Processing successful for {item['title']}.")

                    return {'item': item, 'status': 'success', 'file': moved_path}

            # If we tried the top matches but all failed
            return {'item': item, 'status': 'download_failed'}

        except Exception as e:
            self._log.log("error", f"Error in task for {item['title']}: {e}")
            return {'item': item, 'status': 'error', 'error': str(e)}

    def _move_downloaded_file(self, file, item):
        """
        Moves the downloaded file to the library directory, updates item path.
        """
        try:
            fpath = file['filename']
            fname = os.path.basename(fpath)

            # 1. Find where the file actually landed (since it's maybe in a temp folder)
            dl_fstring = glob.glob(
                f'{self.download_dir}/**/*{glob.escape(fname)}',
                recursive=True
            )
            if not dl_fstring:
                return None
            dl_abspath = Path(dl_fstring[0]).resolve()

            extension = fname.split('.')[-1]
            if dl_abspath:
                # 2. Construct new path
                src = dl_abspath
                dst = self.ssp.item_to_string(item, ext=extension, path=self.library_dir)
                rmv = dl_abspath.parent.absolute()

                # 3. Move or remove existing
                if os.path.exists(dst):
                    self._log.log('debug', f"Dest file {dst} already exists. Deleting source {src}.")
                    os.remove(src)
                else:
                    os.rename(src, dst)

                # 4. Cleanup
                shutil.rmtree(rmv)
                self._log.log('debug', f"File moved to library: {dst}")
                return dst

        except Exception as e:
            self._log.log("error", f"Failed to move file {file['filename']}: {e}")

        return None

    def _get_library_items(self, lib, genres):
        """
        Retrieves library items to process. If genres='all', we gather all genres.
        Otherwise, we split comma-separated genres and query for items lacking a path.
        """
        if not genres:
            genres = 'all'
        genres_list = genres.split(',') if genres != 'all' else sorted(set(i.genre for i in lib.items()))

        # Build queries
        genre_queries = [SubstringQuery('genre', g) for g in genres_list]
        combined_genres = OrQuery(genre_queries)
        path_query = NoneQuery('path')  # items with no path
        final_query = AndQuery([combined_genres, path_query])

        items = list(lib.items(final_query))
        # Maybe reverse them? (As your original code did)
        
        week_ago = datetime.now() - timedelta(days=7)
        
        filtered = []
        for i in items:
            # last_download_attempt is stored as a string (ISO8601) in the DB
            last_download_str = i.get('last_download_attempt', '')
            if last_download_str:
                try:
                    last_download_dt = datetime.fromisoformat(last_download_str)
                    # If it was more recent than a week ago, skip
                    if last_download_dt > week_ago:
                        continue
                except ValueError:
                    # If the string is malformed, treat it as if no attempt
                    pass
            
            # If we get here, either no last_download_attempt or older than a week
            filtered.append(i)

        return filtered[::-1]

    def clean_up(self):
        """
        Cleans up resources and logs summary results.
        """
        self.client.transfers.remove_completed_downloads()

        # Delete all searches
        searches = self.client.searches.get_all()
        for s in searches:
            self.client.searches.delete(s['id'])

        self._log.log("info", "Cleanup completed. Removed completed downloads and searches.")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _search_with_backoff(self, item):
        """
        Perform a search with exponential backoff and controlled throttling.
        """
        async with self.semaphore:
            try:
                self._log.log("debug", f"Initiating search for item: {item['title']}")
                await asyncio.sleep(2)  # Throttle
                results = await self.searcher.perform_search(item)
                self._log.log("debug", f"Search completed for {item['title']}. Results: {len(results)}")
                return results
            except Exception as e:
                self._log.log("debug", f"Search failed for {item['title']}. Error: {e}")
                raise
