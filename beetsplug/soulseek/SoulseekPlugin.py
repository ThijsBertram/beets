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
import os
import shutil
from tenacity import retry, stop_after_attempt, wait_exponential

class SoulSeekPlugin(BeetsPlugin):
    """
    Redesigned SoulSeekPlugin to manage tasks and logging with controlled throttling.
    """

    def __init__(self):
        super().__init__()

        # Initialize the custom logger
        self._log = CustomLogger("SoulSeekPlugin", default_color="cyan")

        # Configuration setup
        self.max_threads = int(self.config['max_threads'].get(1))  # Single thread for requests
        self.dl_timeout = int(self.config['dl_timeout'].get(600))  # Example timeout configuration
        self.download_dir = self.config['slsk_dl_dir'].get()
        self.library_dir = os.path.abspath(config['directory'].get())
        self.host = self.config['host'].get()
        self.api_key = self.config['api_key'].get()

        # Semaphore for rate limiting (single async request at a time)
        self.semaphore = asyncio.Semaphore(2)

        # Downloader and Searcher instances
        self.client = SlskdClient(api_key=self.api_key, host=self.host)  # Replace with actual client initialization
        self.downloader = Downloader(self.client, self._log, self.semaphore, timeout=self.dl_timeout)
        self.searcher = Searcher(self.client, self._log)
        self.ssp = SongStringParser()


        # Components
        self.download_queue = Queue()
        self.results = []  # Store results for later processing

        # Add Beets Subcommand
        self.dl_slsk = Subcommand('dl-slsk', help='Download songs from Soulseek.')
        self.dl_slsk.parser.add_option('--n-tries', dest='tries', default='3')
        self.dl_slsk.parser.add_option('--genres', dest='genres', default='all')
        self.dl_slsk.func = self._start_download_sync  # Use the synchronous wrapper

        self.clean_up()

    def commands(self):
        return [self.dl_slsk]

    def _start_download_sync(self, lib, opts, args):
        """
        Synchronous wrapper to run the asynchronous _start_download function.

        Args:
            lib (Library): Beets library instance.
            opts (Namespace): Command-line options.
            args (list): Additional command-line arguments.
        """
        try:
            asyncio.run(self.download(lib, opts, args))
        except RuntimeError as e:
            self._log.log("error", f"Async runtime error occurred: {e}")

    async def download(self, lib, opts, args):
        """
        Initiates the download process by adding tasks to the queue and executing them.

        Args:
            lib (Library): Beets library instance.
            opts (Namespace): Command-line options.
            args (list): Additional command-line arguments.
        """
        items = self._get_library_items(lib, opts)
        self._log.log("info", f"Found {len(items)} items to download.")

        # Process items iteratively with semaphore for throttling
        self.results = []
        for item in items:
            async with self.semaphore:
                self._log.log("info", f"Processing item: {item['title']}")
                try:
                    result = await self._process_task(item)
                    self.results.append(result)
                    self._log.log("info", f"Task completed successfully for item: {item['title']}")
                except Exception as e:
                    self._log.log("error", f"Error occurred during task execution for item {item['title']}: {e}")

    async def _process_task(self, item):
        try:
            self._log.log("info", f"Starting task for item: {item['title']}")
            results = await self._search_with_backoff(item)
            self._log.log("info", f"Search completed for item: {item['title']}. Results: {len(results)}")

            matches = self.searcher.match_results(results, item)
            if not matches:
                self._log.log("warning", f"No matches found for item: {item['title']}")
                return {'item': item, 'status': 'no_matches'}

            for match in matches[:3]:
                file = await self.downloader.download(match['file'], match['username'])
                self._log.log("info", f"Download attempt for match: {match['file']['filename']}")

                if file:
                    moved_path = self._move_downloaded_file(file, item)
                    # if moved_path:
                    #     self._log.log("info", f"File moved successfully: {moved_path}")
                    #     return {'item': item, 'status': 'success', 'file': moved_path}
                    if moved_path:
                        self._log.log("info", f"File moved successfully: {moved_path}")

                        item['path'] = moved_path
                        item.store()

                        return {'item': item, 'status': 'success', 'file': moved_path}
            return {'item': item, 'status': 'download_failed'}
        except Exception as e:
            self._log.log("error", f"Error in task for item {item['title']}: {e}")
            return {'item': item, 'status': 'error', 'error': str(e)}

    def _move_downloaded_file(self, file, item):
        """
        Moves the downloaded file to the library directory.

        Args:
            file (dict): File metadata of the downloaded file.
            item (dict): Song metadata.

        Returns:
            str or None: New path of the moved file, or None if the move failed.
        """
        try:
            # 5. MOVE FILE
            # 5.0 process filename stuff - prepare moving 
            fpath = file['filename']
            fname = fpath.split('\\')[-1]
            dl_fstring = glob.glob(f'{self.download_dir}/**/*{glob.escape(fname)}', recursive=True)  


            # ugly piece of code - fix this 
            try:
                dl_fstring = dl_fstring[0]
            except IndexError:
                return False
            dl_abspath = Path(dl_fstring).resolve()
            extension = fname.split('.')[-1]



            # 5.5 move file
            # MOVE FILE
            if dl_abspath:
                # CONSTRUCT PATHS
                src = dl_abspath
                dst = self.ssp.string_from_item(item, ext=extension, path=self.library_dir)
                rmv = dl_abspath.parent.absolute()

                if os.path.exists(dst):
                    self._log.log('info', f"Destination file {dst} already exists. Deleting the source file {src}.")
                    os.remove(src)
                else:
                    os.rename(src, dst)
                                
                # delete placeholder dir
                shutil.rmtree(rmv)
                self._log.log('info', f"File succesfully moved to audio library: {dst}")
                return dst
        except Exception as e:
            # self.dls[item.id]['status'] = 'move_failed'
            self._log.log("error", f"Failed to move file {file['filename']}: {e}")

            return False

    def _get_library_items(self, lib, opts):
        """
        Retrieves library items to process based on command-line options.

        Args:
            lib (Library): Beets library instance.
            opts (Namespace): Command-line options.

        Returns:
            list: A list of library items to process.
        """
        genres_to_dl = opts.genres.split(',') if opts.genres else list()
        if genres_to_dl == ['all']:
            genres_to_dl = sorted(list(set([item.genre for item in lib.items()])))

        genre_query = list()
        for genre in genres_to_dl:
            substring_query = SubstringQuery('genre', genre)
            genre_query.append(substring_query)

        path_query = NoneQuery('path')
        genre_query = OrQuery(genre_query)

        query = AndQuery([genre_query, path_query])

        items = [item for item in lib.items(query)]
        return items

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
    async def _search_with_backoff(self, query):
        """
        Perform a search with exponential backoff and controlled throttling.

        Args:
            query (str): The search query.

        Returns:
            list: The search results.
        """
        async with self.semaphore:
            try:
                self._log.log("info", f"Initiating search for query: {query}")
                await asyncio.sleep(2)  # Throttle requests
                results = await self.searcher.perform_search(query)
                self._log.log("info", f"Search completed for query: {query}. Results: {len(results)}")
                return results
            except Exception as e:
                self._log.log("error", f"Search failed for query: {query}. Error: {e}")
                raise





# from concurrent.futures import ThreadPoolExecutor, as_completed
# from queue import Queue
# from beetsplug.custom_logger import CustomLogger

# # Beets
# from beets.plugins import BeetsPlugin
# from beets.ui import Subcommand
# from beets import config
# from beets.dbcore.query import SubstringQuery, OrQuery, AndQuery, NoneQuery

# import asyncio
# from .download import Downloader
# from .search import Searcher
# from slskd_api import SlskdClient

# from pathlib import Path
# import os
# import shutil
# from tenacity import retry, stop_after_attempt, wait_exponential


# class SoulSeekPlugin(BeetsPlugin):
#     """
#     Redesigned SoulSeekPlugin to manage tasks and logging with controlled throttling.
#     """

#     def __init__(self):
#         super().__init__()

#         # Initialize the custom logger
#         self._log = CustomLogger("SoulSeekPlugin", default_color="cyan")

#         # Configuration setup
#         self.max_threads = int(self.config['max_threads'].get(1))  # Single thread for requests
#         self.dl_timeout = int(self.config['dl_timeout'].get(600))  # Example timeout configuration
#         self.download_dir = os.path.abspath(self.config['slsk_dl_dir'].get())
#         self.library_dir = os.path.abspath(config['directory'].get())
#         self.host = self.config['host'].get()
#         self.api_key = self.config['api_key'].get()

#         # Downloader and Searcher instances
#         self.client = SlskdClient(api_key=self.api_key, host=self.host)  # Replace with actual client initialization
#         self.downloader = Downloader(self.client, self._log, timeout=self.dl_timeout)
#         self.searcher = Searcher(self.client, self._log)

#         # Semaphore for rate limiting (single async request at a time)
#         self.semaphore = asyncio.Semaphore(1)

#         # Components
#         self.download_queue = Queue()
#         self.results = []  # Store results for later processing

#         # Add Beets Subcommand
#         self.dl_slsk = Subcommand('dl-slsk', help='Download songs from Soulseek.')
#         self.dl_slsk.parser.add_option('--n-tries', dest='tries', default='3')
#         self.dl_slsk.parser.add_option('--genres', dest='genres', default='all')
#         self.dl_slsk.func = self.download

#         self.clean_up()

#     def commands(self):
#         return [self.dl_slsk]

#     @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=10, max=60))
#     async def _search_with_backoff(self, query):
#         """
#         Perform a search with exponential backoff and controlled throttling.

#         Args:
#             query (str): The search query.

#         Returns:
#             dict: The search results.
#         """
#         async with self.semaphore:
#             self._log.log("info", f"Performing search for query: {query}")
#             await asyncio.sleep(2)  # Throttle requests significantly
#             search_results = await self.searcher.perform_search(query)

#             # Ensure search_results is a valid response and not directly a dict
#             if isinstance(search_results, dict):
#                 self._log.log("error", f"Unexpected non-awaitable object returned: {search_results}")
#                 raise TypeError("Non-awaitable object returned from perform_search.")

#             return search_results

#     async def download(self, lib, opts, args):
#         """
#         Initiates the download process by adding tasks to the queue and executing them.

#         Args:
#             lib (Library): Beets library instance.
#             opts (Namespace): Command-line options.
#             args (list): Additional command-line arguments.
#         """
#         items = self._get_library_items(lib, opts)
#         self._log.log("info", f"Found {len(items)} items to download.")

#         tasks = [self._process_task(item) for item in items]
#         self.results = await asyncio.gather(*tasks, return_exceptions=True)

#         for result in self.results:
#             if isinstance(result, Exception):
#                 self._log.log("error", f"Error occurred during task execution: {result}")
#             else:
#                 self._log.log("info", f"Task completed successfully: {result}")


#     # def download(self, lib, opts, args):
#     #     """
#     #     Initiates the download process by adding tasks to the queue and executing them.

#     #     Args:
#     #         lib (Library): Beets library instance.
#     #         opts (Namespace): Command-line options.
#     #         args (list): Additional command-line arguments.
#     #     """
#     #     items = self._get_library_items(lib, opts)
#     #     self._log.log("info", f"Found {len(items)} items to download.")

#     #     # Add items to the download queue
#     #     for item in items:
#     #         self.download_queue.put(item)

#     #     # Process the download queue sequentially
#     #     for item in items:
#     #         try:
#     #             result = self._process_task(item)
#     #             self.results.append(result)
#     #             self._log.log("info", f"Completed task for item: {item['title']}")
#     #         except Exception as e:
#     #             self._log.log("error", f"Error processing item {item['title']}: {e}")

#     # def _process_task(self, item):
#     #     """
#     #     Handles the end-to-end processing of a single item.

#     #     Args:
#     #         item (dict): A single library item to process.

#     #     Returns:
#     #         dict: The result of the processing task.
#     #     """
#     #     try:
#     #         self._log.log("info", f"Starting task for item: {item['title']}")
#     #         results = asyncio.run(self._search_with_backoff(item))

#     #         if not results:
#     #             self._log.log("warning", f"No results found for item: {item['title']}")
#     #             return {'item': item, 'status': 'no_results'}

#     #         matches = self.searcher.match_results(results, item)
#     #         if not matches:
#     #             self._log.log("warning", f"No matches found for item: {item['title']}")
#     #             return {'item': item, 'status': 'no_matches'}

#     #         for match in matches[:3]:  # Limit to top 3 matches
#     #             file = self.downloader.download(match, item['artist'])
#     #             if file:
#     #                 moved_path = self._move_downloaded_file(file, item)
#     #                 if moved_path:
#     #                     self._log.log("info", f"Download successful and moved for item: {item['title']}")
#     #                     return {'item': item, 'status': 'success', 'file': moved_path}

#     #         self._log.log("warning", f"Download failed for item: {item['title']}")
#     #         return {'item': item, 'status': 'download_failed'}
#     #     except Exception as e:
#     #         self._log.log("error", f"Error in task for item {item['title']}: {e}")
#     #         return {'item': item, 'status': 'error', 'error': str(e)}

#     async def _process_task(self, item):
#         """
#         Handles the end-to-end processing of a single item.

#         Args:
#             item (dict): A single library item to process.

#         Returns:
#             dict: The result of the processing task.
#         """
#         try:
#             self._log.log("info", f"Starting task for item: {item['title']}")
            
#             # Perform the search with backoff
#             results = await self._search_with_backoff(item['title'])

#             if not results:
#                 self._log.log("warning", f"No results found for item: {item['title']}")
#                 return {'item': item, 'status': 'no_results'}

#             matches = self.searcher.match_results(results, item)
#             if not matches:
#                 self._log.log("warning", f"No matches found for item: {item['title']}")
#                 return {'item': item, 'status': 'no_matches'}

#             for match in matches[:3]:  # Limit to top 3 matches
#                 file = await self.downloader.download(match, match['username'])  # Await the async download method
#                 if file:
#                     moved_path = self._move_downloaded_file(file, item)
#                     if moved_path:
#                         self._log.log("info", f"Download successful and moved for item: {item['title']}")
#                         return {'item': item, 'status': 'success', 'file': moved_path}

#             self._log.log("warning", f"Download failed for item: {item['title']}")
#             return {'item': item, 'status': 'download_failed'}
#         except Exception as e:
#             self._log.log("error", f"Error in task for item {item['title']}: {e}")
#             return {'item': item, 'status': 'error', 'error': str(e)}


#     def _move_downloaded_file(self, file, item):
#         """
#         Moves the downloaded file to the library directory.

#         Args:
#             file (dict): File metadata of the downloaded file.
#             item (dict): Song metadata.

#         Returns:
#             str or None: New path of the moved file, or None if the move failed.
#         """
#         try:
#             file_path = Path(file['filename']).resolve()
#             file_name = file_path.name
#             extension = file_path.suffix

#             destination_path = Path(self.library_dir) / f"{item['artist']} - {item['title']}{extension}"

#             if destination_path.exists():
#                 self._log.log("warning", f"Destination file {destination_path} already exists. Deleting the source file.")
#                 file_path.unlink()
#                 return None

#             shutil.move(str(file_path), str(destination_path))

#             # Remove the parent directory if empty
#             parent_dir = file_path.parent
#             if parent_dir.exists() and not any(parent_dir.iterdir()):
#                 parent_dir.rmdir()

#             return str(destination_path)
#         except Exception as e:
#             self._log.log("error", f"Failed to move file {file['filename']}: {e}")
#             return None

#     def _get_library_items(self, lib, opts):
#         """
#         Retrieves library items to process based on command-line options.

#         Args:
#             lib (Library): Beets library instance.
#             opts (Namespace): Command-line options.

#         Returns:
#             list: A list of library items to process.
#         """
#         genres_to_dl = opts.genres.split(',') if opts.genres else list()
#         if genres_to_dl == ['all']:
#             genres_to_dl = sorted(list(set([item.genre for item in lib.items()])))

#         genre_query = list()
#         for genre in genres_to_dl:
#             substring_query = SubstringQuery('genre', genre)
#             genre_query.append(substring_query)

#         path_query = NoneQuery('path')
#         genre_query = OrQuery(genre_query)

#         query = AndQuery([genre_query, path_query])

#         items = [item for item in lib.items(query)]
#         return items

#     def clean_up(self):
#         """
#         Cleans up resources and logs summary results.
#         """
#         self.client.transfers.remove_completed_downloads()

#         # Delete all searches
#         searches = self.client.searches.get_all()
#         for s in searches:
#             self.client.searches.delete(s['id'])

#         self._log.log("info", "Cleanup completed. Removed completed downloads and searches.")