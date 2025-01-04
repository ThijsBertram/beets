from slskd_api import SlskdClient

from datetime import datetime
import os
import time
from slskd_api.apis import SearchesApi
from collections import deque
from datetime import datetime
import time
from tenacity import retry, stop_after_attempt, wait_fixed
import logging

api_key = 'AAAAB3NzaC1yc2EAAAADAQABAAABgQC+wrcS6ePBpKs1E9C04/q+VE+NLGcBJZFD1qdX+j2rmxPB5Y9c7XsQ6Yd68rqc2GODKLVfvlERe'
max_threads = 3
slsk_dl_dir = 'D:\\SOULSEEK\\slskd\\src\\downloads'
host = 'http://localhost:5030'
dl_timeout = 600



class Downloader:
    """
    A class to handle downloading on Soulseek.

    Attributes:
    client : SlskdClient
        The Soulseek client used to perform downloads.

    Methods:
    download(match)
        Downloads a matched song.
    move_file(src, dest)
        Moves the downloaded file to the designated location.
    """

    def __init__(self, client, log, timeout):
        self.transfer_api = client.transfers
        self._log = log
        self.dl_timeout = timeout

    def download(self, match, username):

        timeout = time.perf_counter() + self.dl_timeout
        """Downloads a matched song."""
        try:
            download_attempted_at = datetime.now()
            download = self.transfer_api.enqueue(username, [match])    
            f = match['filename'].split('\\')[-1]
            self._log.info(f"Download started: {f}")        
            while True:
                if time.perf_counter() > timeout:
                    self._log.error(f"Download timeout: {f} after {self.dl_timeout} seconds")
                    return None, download_attempted_at
                # status = self.transfer_api.state(download_id)
                file = self.check_download_state(username=username, f=f)
                if not file:
                    time.sleep(1)
                    continue
                elif file['state'] == 'Completed, Succeeded':
                    self._log.info(f"Download complete: {f}")
                    return file, download_attempted_at
                elif file['state'] == 'Queued, Remotely':
                    self._log.info(f"Download queued remotely: {f}")
                    return None, download_attempted_at
                elif file['state'] == 'Completed, Errored':
                    self._log.info(f"Download errored: {f}")
                    return None, download_attempted_at
                else: 
                    self._log.error(f"Download failed: {f}")
                    return None, download_attempted_at
        except Exception as e:
            self._log.error(f"Download error: {e}")
            raise


    def check_download_state(self, username, f):
        # download = self.transfer_api.get(download(self.dl_username, self.dl_file))
        downloads = self.transfer_api.get_all_downloads()
        dl_from_username = [download for download in downloads if download['username'] == username]


        for dl in dl_from_username:

            file = dl['directories'][0]['files'][0]
            completed = 1 if file['state'] == 'Completed, Succeeded' else 0
            fname = file['filename'].split('\\')[-1]
            username = file['username']


            print("DOWNLOAD STAUTS")
            print(file['state'])
            print(fname)
            print(f)
            print(fname == f)
            print()

            if (fname == f):
                return file


class Searcher:
    """
    A class to handle searching on Soulseek.

    Attributes:
    client : SlskdClient
        The Soulseek client used to perform searches.

    Methods:
    create_queries(song)
        Creates search queries from the song dictionary.
    search_soulseek(query)
        Initiates a search on Soulseek.
    search_finished(search_id)
        Checks if the search is finished.
    get_search_results(search_id)
        Retrieves search results from Soulseek.
    perform_search(song)
        Performs the search and returns results.
    match_results(matches, song)
        Matches search results to the song.
    """

    def __init__(self, client, log):
        self.search_api = client.searches
        self._log = log

    def create_queries(self, item):
        """Creates search queries from the song dictionary."""
        simple= ' '.join([item[k] for k in ['main_artist', 'feat_artist', 'song_title', 'remixer', 'remix_type' ] if item[k]])
        simpler = ' '.join([item[k] for k in ['main_artist', 'song_title',  'remixer'] if item[k]])
        simplest = ' '.join([item[k] for k in ['main_artist', 'song_title'] if item[k]])
        return deque([simple, simpler, simplest])

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def search_soulseek(self, query):
        """Initiates a search on Soulseek."""
        try:
            search = self.search_api.search_text(query)
            return search['id']
        except Exception as e:
            self._log.error(f"Search error: {e}")
            raise

    def search_finished(self, search_id):
        """Checks if the search is finished."""
        try:
            s = self.search_api.state(search_id)
            return s['isComplete']
        except Exception as e:
            self._log.debug(f"Search state error: {e}")
            return False

    def get_search_results(self, search_id):
        """Retrieves search results from Soulseek."""
        try:
            results = self.search_api.search_responses(search_id)
            return results
        except Exception as e:
            self._log.error(f"Get search results error: {e}")
            return []

    def perform_search(self, item):
        """Performs the search and returns results."""

        song = {
            "main_artist": item['main_artist'],
            "song_title": item['title'],
            "feat_artist": item['feat_artist'],
            "remixer": item['remixer'],
            "remix_type": item['remix_type']
        }
        try:
            queries = self.create_queries(song)
            queries = sorted(list(set(queries)))
            search_attempted_at = datetime.now()
            for query in queries:
                search_id = self.search_soulseek(query)
                if search_id:
                    while not self.search_finished(search_id):
                        time.sleep(1)
                    results = self.get_search_results(search_id)
                    if results:
                        # self._log.info(f"Search query: {query}, Results found: {len(results)}")
                        return results, search_attempted_at
            return [], search_attempted_at
        except Exception as e:
            self._log.error(f"Error in perform_search: {e}")
            raise
    
    def match_results(self, search_results, item):
        """"Matches search results to the song.
        
        Keyword arguments:
        argument -- description
        Return: return_description
        """
        
        song = {
            "main_artist": item['main_artist'],
            "song_title": item['title'],
            "feat_artist": item['feat_artist'],
            "remixer": item['remixer'],
            "remix_type": item['remix_type']
        }

        # 1. FILTER POTENTIAL MATCHES (and store as list of dicts)
        #   > remove locked files
        #   > remove files missing information
        potential_matches = list()

        for i, user_files in enumerate(search_results):
            username = user_files['username']
            for result in user_files['files']:
                
                file = dict()
                
                
                # FILTER m4a - FIX THIS MAKE IT GENERAL NOT HARDCODED UGLY UGLY UGLY CODE
                if 'm4a' in result['extension'].lower():
                    continue

                # LOCKED FILE
                try:
                    assert result['isLocked'] == False
                except AssertionError:
                    self._log.debug(f"Mismatch - file is locked - {result['filename']}") 
                    continue
                # KEYS PRESENT   
                try:
                    assert len(set(result.keys()).intersection(set(['filename', 'length', 'extension', 'bitRate', 'bitDepth']))) >= 4
                except AssertionError:
                    self._log.debug(f"Mismatch - keys missing - {result['filename']}")
                    continue
                # BITRATE
                try:
                    bitrate = result['bitRate'] if 'bitRate' in result.keys() else result['bitDepth'] * 44
                    potential_matches.append((username, result, bitrate))
                except KeyError:
                    self._log.debug(f"Mismatch - bitrate missing - {result['filename']}")
                    continue


                

        # 2. FILTER OUT SONGS THAT MISMATCH ON SONG INFO
        # main artist & title
        matches = [match for match in potential_matches if song['main_artist'].lower() in match[1]['filename'].lower() and song['song_title'].lower() in match[1]['filename'].lower()]
        # remix artist
        if song['remixer']:
            matches = [match for match in matches if song['remixer'].lower() in match[1]['filename'].lower()]
        # feat artist
        if song['feat_artist']:
            matches = [match for match in matches if song['feat_artist'].lower() in match[1]['filename'].lower()]
        # 3. FILTER OUT SONGS BASED ON LENGTH
        # match for match in matches if match['length'] ............. 

        # 3. ORDER SONGS BASED ON BITRA
        matches = sorted(matches, key=lambda x: x[2], reverse=True)

        
        return [(match[0], match[1]) for match in matches]
        # return matches[0]


_log = logging.getLogger(__name__)

slsk = SlskdClient(api_key=api_key, host=host)
searcher = Searcher(slsk, log=_log)
downloader = Downloader(slsk, log=_log, timeout=dl_timeout)



downloader.check_download_state('MikeyC4', 'filename')