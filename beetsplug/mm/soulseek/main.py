import threading
from queue import Queue
from datetime import datetime
from loguru import logger
import os

from slskd_api import SlskdClient
from soulseek.download import Downloader
from soulseek.search import Searcher
from database.models import SoulseekModel
from dotenv import load_dotenv

from utils.song_string import dict_to_string
from playhouse.shortcuts import model_to_dict, dict_to_model

load_dotenv()

API_KEY = os.environ['SOULSEEK_API_KEY']
BASE_PATH = os.environ.get('BASE_PATH', '/downloads')
MAX_THREADS = int(os.environ.get('MAX_THREADS', 5))
LIBRARY_DIR = os.environ.get('LIBRARY_DIR')
SOULSEEK_DL_DIR = os.environ.get('SOULSEEK_DL_DIR')

slskd_client = SlskdClient(api_key=os.environ.get('SOULSEEK_API_KEY'), host='http://localhost:5030')


class SoulseekDownloader:
    """
    The main class to handle the entire download process from searching to downloading.

    Attributes:
    client : SlskdClient
        The Soulseek client used for searching and downloading.
    searcher : Searcher
        The searcher object to handle search operations.
    downloader : Downloader
        The downloader object to handle download operations.
    download_queue : Queue
        The queue to manage the download tasks.
    threads : list
        The list of threads for concurrent downloads.
    stop_event : threading.Event
        The event to signal stopping the threads.
    """

    def __init__(self, client, max_threads=MAX_THREADS):
        self.client = client
        self.searcher = Searcher(client)
        self.downloader = Downloader(client)
        self.download_queue = Queue()
        self.max_threads = max_threads
        self.threads = []
        self.stop_event = threading.Event()
        logger.add("logs/soulseek_downloader.log", rotation="1 MB", level="INFO")

    def handle_download(self):
        """Handles the download tasks from the queue."""
        while not self.stop_event.is_set():
            try:
                song = self.download_queue.get(timeout=1)  # 1 second timeout
            except:
                continue  # If queue is empty, continue checking

            if song is None:
                break

            try:
                # Search song
                results, search_attempted_at = self.searcher.perform_search(song)
                search_data = {
                    'song_id': song['song_id'],
                    'search_attempted_at': search_attempted_at,
                    'download_attempted_at': datetime.now()  # Default in case of no matches or results
                }
                # Match search results
                if results:
                    matches = self.searcher.match_results(results, song)
                    search_data.update({
                        'results_found': str(len(results)),
                        'matches_found': str(len(matches))
                    })
                    # Download match
                    if matches:
                        for match in matches:
                            username, match_data = match
                            file, download_attempted_at = self.downloader.download(match=match_data,
                                                                                  username=username)

                            file_path = file['filename']
                            folder = file_path.split('\\')[-2]
                            f = file_path.split('\\')[-1]
                            extension = f.split('.')[-1]
                            song['extension'] = extension

                            # MOVE THE FILE
                            if file_path:
                                # SOURCE
                                src = os.path.join(SOULSEEK_DL_DIR, folder, f)
                                # DESTINATION
                                dst_filename = dict_to_string(song, mode='filename')
                                dst = os.path.join(LIBRARY_DIR, dst_filename)
                                # MOVE
                                self.downloader.move_file(src, dst)
                                # DELETE FOLDER
                                os.remove(os.path.join(SOULSEEK_DL_DIR, folder))


                                search_data.update({
                                    'search_query': match[1]['filename'],
                                    'file': os.path.basename(file_path),
                                    'folder': folder,
                                    'download_status': 'success',
                                    'download_attempted_at': download_attempted_at
                                })
                                break
                        else:
                            search_data.update({
                                'search_query': 'N/A',
                                'file': 'N/A',
                                'folder': 'N/A',
                                'download_status': 'no matches'
                            })
                    else:
                        search_data.update({
                            'search_query': 'N/A',
                            'file': 'N/A',
                            'folder': 'N/A',
                            'download_status': 'no matches'
                        })
                else:
                    search_data.update({
                        'results_found': '0',
                        'matches_found': '0',
                        'search_query': 'N/A',
                        'file': 'N/A',
                        'folder': 'N/A',
                        'download_status': 'no results'
                    })

                SoulseekModel.create(**search_data)

            except Exception as e:
                logger.error(f"Error in handle_downloads: {e}")
            finally:
                self.download_queue.task_done()

        logger.info("Thread exiting...")

    def add_to_queue(self, song):
        """Adds a list of songs to the download queue."""

        def queue(song):
            if isinstance(song, dict):
                self.download_queue.put(song)
            elif str(type(song)) == '<Model: SongModel>':
                song = model_to_dict(song)
                self.download_queue.put(song)
            else:
                logger.error(f"Error in adding song to queue, wrong type: {type(song)}")
            return

        if isinstance(song, list):
            for s in song:
                queue(s)
       
        return

    def get_songs(self):
        """Wrapper to start threads and ensure they stop when the queue is empty."""
        # start threads
        self.stop_event.clear()
        for _ in range(self.max_threads):
            t = threading.Thread(target=self.handle_download)
            t.daemon = True
            t.start()
            self.threads.append(t)
        # Wait for all tasks to be completed
        self.download_queue.join()          
        # Stops the download threads
        self.stop_event.set()               
        for _ in range(len(self.threads)):
            self.download_queue.put(None)
        for t in self.threads:
            t.join()
        self.threads.clear()