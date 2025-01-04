# Beets
from beets.plugins import BeetsPlugin
from beets.library import Library
from beets.ui import Subcommand
from beets import config
from beetsplug.ssp import SongStringParser
from beets.dbcore.query import AndQuery, RegexpQuery, OrQuery, SubstringQuery, NotQuery, NoneQuery

# Varia'
import re
import os
import glob
import time
import shutil
import logging
import datetime


import pathlib
import threading
from queue import Queue, Empty
from datetime import datetime

from slskd_api import SlskdClient
from .download import Downloader
from .search import Searcher
# from .models import SoulseekModel
# from dotenv import load_dotenv

import colorlog

# ANSI Escape Codes for Green Shades
GREEN_BRIGHT = '\033[92m'   # Bright Green
GREEN = '\033[38;5;154m'  # Lime Green
GREEN_DARK = '\033[32m'     # Dark Green

RED_BRIGHT = '\033[91m'     # Bright Red
RED = '\033[31m'       # Dark Red
RED_DARK = '\033[38;5;203m'  # Light Red

# ANSI Escape Codes for Blue Shades
BLUE_BRIGHT = '\033[94m'    # Bright Blue
BLUE = '\033[38;5;111m' # Sky Blue
BLUE_DARK = '\033[34m'      # Dark Blue

# ANSI Escape Codes for Cyan Shades
CYAN_BRIGHT = '\033[96m'    # Bright Cyan
CYAN = '\033[38;5;51m' # Aqua
CYAN_DARK = '\033[38;5;44m' # Teal

# ANSI Escape Codes for Yellow Shades
YELLOW_BRIGHT = '\033[93m'  # Bright Yellow
YELLOW = '\033[38;5;220m' # Golden Yellow
YELLOW_DARK = '\033[33m'    # Dark Yellow

# Reset ANSI Formatting
RESET = '\033[0m'

PLATFORM_LOG_COLOR = {
    'spotify': GREEN,
    'youtube': RED
}

        



class SoulSeekPlugin(BeetsPlugin):
    
    def __init__(self):

        super().__init__()
        self._log = logging.getLogger('beets.soulseek')

        # Add a simple console handler
        console_handler = logging.StreamHandler()
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        console_handler.setFormatter(formatter)
        self._log.addHandler(console_handler)
        self._log.propagate = False

        self.ssp = SongStringParser()

        # CONFIG
        self.api_key = self.config['api_key'].get()
        self.max_threads = int(self.config['max_threads'].get())
        self.library_dir = os.path.abspath(config['directory'].get())
        self.slsk_dl_dir = os.path.abspath(self.config['slsk_dl_dir'].get())
        self.host = self.config['host'].get()
        self.dl_timeout = int(self.config['dl_timeout'].get())

        # Objects
        self.slsk = SlskdClient(api_key=self.api_key, host=self.host)
        self.searcher = Searcher(self.slsk, log=self._log)
        self.downloader = Downloader(self.slsk, log=self._log, timeout=self.dl_timeout)
        self.download_queue = Queue()
        self.threads = list()
        self.stop_event = threading.Event()

        # Central command definitions
        self.dl_slsk = Subcommand('dl-slsk', help='Download songs from Soulseek.')
        self.dl_slsk.parser.add_option('--n-tries', dest='tries', default='3')
        self.dl_slsk.parser.add_option('--genres', dest='genres', default='all')	
        self.dl_slsk.func = self.download

        # Results
        self.dls = dict()

    def commands(self):
        return [self.dl_slsk]
    
    
    def download(self, lib, opts, args):
        print("DOWNLOADING")


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

        unique_genres = set([item.genre for item in items])

        self.add_to_queue(items)

        self.get_songs()

        # ADD SUCCESFUL DLS TO LIBRARY
        success = [i for i in self.dls.values() if i['status'] == 'success']
        no_results = [i for i in self.dls.values() if i['status'] == 'no_results']
        no_matches = [i for i in self.dls.values() if i['status'] == 'no_matches']
        dl_failed = [i for i in self.dls.values() if i['status'] == 'dl_failed']
        move_failed = [i for i in self.dls.values() if i['status'] == 'move_failed']
        not_finished = [i for i in self.dls.values() if i['status'] == 'not_finished']
        
        self._log.info(" DOWNLOAD RESULTS")
        self._log.info(f"{YELLOW}{len(success)}{RESET} - {GREEN}SUCCESS{RESET}")
        self._log.info(f"{YELLOW}{len(no_results)}{RESET} - NO RESULTS{RESET}")
        self._log.info(f"{YELLOW}{len(no_matches)}{RESET} - {YELLOW_DARK}NO MATCHES{RESET}")
        self._log.info(f"{YELLOW}{len(dl_failed)}{RESET} - {RED}DOWNLOAD FAILED{RESET}")
        self._log.info(f"{YELLOW}{len(move_failed)}{RESET} - {RED_BRIGHT}MOVING FAILED{RESET}")
        self._log.info(f"{YELLOW}{len(not_finished)}{RESET} - {RED_DARK}NOT FINISHED{RESET}")
        self._log.info(f"{YELLOW}{len(success)}{RESET} / {YELLOW}{len(self.dls.values())}{RESET} SUCCESSFUL{RESET}")
        self._log.info()
        
        return 
    
    
    
    def get_songs(self):
        """Wrapper to start threads and ensure they stop when the queue is empty."""
        
        self.clean_slsk()

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

        """Wrapper to start threads and ensure they stop when the queue is empty."""

        return
            
    def get_item(self):
        item = self.download_queue.get(timeout=1)
        item_id = item.id
        self.dls[item.id] = dict()
        self.dls[item.id]['item'] = item
        self.dls[item.id]['status'] = 'started'

        title = self.dls[item.id]['item']['title']
        self._log.info(f'THREAD - {YELLOW}{title}{RESET} - STARTED')
        return item, item_id
    
    def get_results(self, item, item_id):
        results, search_attempted_at = self.searcher.perform_search(item)
        if not results:
            self.dls[item_id]['status'] = 'no_results'
            # self.download_queue.task_done()
            return False
        else:
            self.dls[item_id]['status'] = 'results'
            n_results = len(results)
            self.dls[item.id]['n_results'] = n_results
            return results
        
    def get_matches(self, results, item):
        matches = self.searcher.match_results(results, item)
        if not matches:
            self.dls[item.id]['status'] = 'no_matches'
            # self.download_queue.task_done()
            return False
        n_matches = len(matches)
        self.dls[item.id]['n_mathces'] = n_matches

        return matches
    
    def get_download(self, match, item):
        # match data
        username, match_data = match
        # download file
        file, download_attempted_at = self.downloader.download(match=match_data,
                                                                username=username)
        # check 
        if not file:
            self.dls[item.id]['status'] = 'dl_failed'
            return False
        return file

    def move_dl(self, file, item):
        try:
            # 5. MOVE FILE
            # 5.0 process filename stuff - prepare moving 
            fpath = file['filename']
            fname = fpath.split('\\')[-1]
            dl_fstring = glob.glob(f'{self.slsk_dl_dir}/**/*{fname}')  

            # ugly piece of code - fix this 
            try:
                dl_fstring = dl_fstring[0]
            except IndexError:
                return False
            dl_abspath = pathlib.Path(dl_fstring).resolve()
            extension = fname.split('.')[-1]
            # 5.5 move file
            # MOVE FILE
            if dl_abspath:
                # CONSTRUCT PATHS
                src = dl_abspath
                dst = self.ssp.string_from_item(item, ext=extension, path=self.library_dir)
                rmv = dl_abspath.parent.absolute()


                if os.path.exists(dst):
                    self._log.debug(f"Destination file {dst} already exists. Deleting the source file {src}.")
                    os.remove(src)
                else:
                    os.rename(src, dst)
                                
                # delete placeholder dir
                shutil.rmtree(rmv)

                self.dls[item.id]['path'] = dst
                self.dls[item.id]['status'] = 'success'
                return dst
        except:
            self.dls[item.id]['status'] = 'move_failed'
            return False
        
    def handle_download(self):
        """Handles the download tasks from the queue."""
        # MAIN LOOP
        while not self.stop_event.is_set():
            results = None
            n_results = None
            matches = None
            n_matches = None
            item = None
            item_id = None
            title = None
            file = None
            
            try:
                # 1. ITEM - taken from queue
                item, item_id = self.get_item()
                if not item:
                    continue
                # 2. RESULTS for slsk item search
                results = self.get_results(item, item_id)
                if not results:
                    continue
                # 3. MATCH - results agains the item
                matches = self.get_matches(results, item)
                if not matches:
                    continue
                # 4. DOWNLOAD - best matches
                for match in matches[:1]:                   # [:3] REPLACE WITH CONFIG VALUE
                    file = self.get_download(match, item)
                    if file['state'] != 'Completed, Succeeded':
                        continue

                # 5. MOVE - downloaded files
                    path = self.move_dl(file, item)
                    if not path:
                        continue          
     
                # 6. ADD PATH - downloaded files
                    item.path = path
                    item.store()

                # -
            except Exception as e:
                if item:
                    self._log.error(f"{item_id} - {YELLOW}{self.dls[item.id]['title']}{RESET} - {RED}ERROR - {e}{RESET}")
                continue
            # used for joining queue ( can be prettier )
            except AttributeError:
                pass
            finally:
                # UGLY UGLY UGLY
                if not item:
                    continue

                status = self.dls[item.id]['status']        
                title = self.dls[item.id]['item']['title']
                if status == 'no_results':
                    self._log.info(f'{item_id} - {YELLOW}{title}{RESET} - no results')
                elif status == 'no_matches':
                    self._log.info(f'{item_id} - {YELLOW}{title}{RESET} - no matches')
                elif status == 'download_failed':
                    self._log.error(f'{item_id} - {YELLOW}{title}{RESET} - {RED}dl failed{RESET}')
                elif status == 'started':
                    self._log.error(f'{item_id} - {YELLOW}{title}{RESET} - {RED}not finished{RESET}')
                elif status == 'move_failed':
                    self._log.error(f'{item_id} - {YELLOW}{title}{RESET} - {RED}not finished{RESET}')
                elif status == 'success':
                    self._log.info(f'{item_id} - {YELLOW}{title}{RESET} - {GREEN}download complete{RESET}')
                self.download_queue.task_done()


        return

    def add_to_queue(self, item):
        """Adds a list of songs to the download queue."""

        def queue(song):
            self.download_queue.put(song)

        if isinstance(item, list):
            self._log.debug(f'ALL THREADS - {[i.id for i in item]} - {len([item])} TOTAL')
            for i in item:
                queue(i)
                time.sleep(0.1)
       
        return
    
    def clean_slsk(self):

        # slsk - downloads
        self.slsk.transfers.remove_completed_downloads()

        # slsk - searches
        searches = self.slsk.searches.get_all()
        for s in searches:
            self.slsk.searches.delete(s['id'])

        # slsk - dl directory
        return