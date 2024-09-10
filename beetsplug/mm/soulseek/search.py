from slskd_api.apis import SearchesApi
from collections import deque
from datetime import datetime
import time
from tenacity import retry, stop_after_attempt, wait_fixed

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

    def __init__(self, client):
        self.search_api = client.searches

    def create_queries(self, song):
        """Creates search queries from the song dictionary."""
        simple = dict_to_string(song, mode='simple')
        simpler = dict_to_string(song, mode='simpler')
        simplest = dict_to_string(song, mode='simplest')
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
            self._log.error(f"Search state error: {e}")
            return False

    def get_search_results(self, search_id):
        """Retrieves search results from Soulseek."""
        try:
            results = self.search_api.search_responses(search_id)
            return results
        except Exception as e:
            self._log.error(f"Get search results error: {e}")
            return []

    def perform_search(self, song):
        """Performs the search and returns results."""
        try:
            queries = self.create_queries(song)
            search_attempted_at = datetime.now()
            for query in queries:
                search_id = self.search_soulseek(query)
                if search_id:
                    while not self.search_finished(search_id):
                        time.sleep(1)
                    results = self.get_search_results(search_id)
                    if results:
                        self._log.info(f"Search query: {query}, Results found: {len(results)}")
                        return results, search_attempted_at
            return None, search_attempted_at
        except Exception as e:
            self._log.error(f"Error in perform_search: {e}")
            raise
    
    def match_results(self, search_results, song):
        """"Matches search results to the song.
        
        Keyword arguments:
        argument -- description
        Return: return_description
        """
        
        # 1. FILTER POTENTIAL MATCHES (and store as list of dicts)
        #   > remove locked files
        #   > remove files missing information
        potential_matches = list()

        for i, user_files in enumerate(search_results):
            username = user_files['username']
            for result in user_files['files']:
                file = dict()
                # LOCKED FILE
                try:
                    assert result['isLocked'] == False
                except AssertionError:
                    self._log.warning(f"Mismatch - file is locked - {result['filename']}") 
                    continue
                # KEYS PRESENT   
                try:
                    assert len(set(result.keys()).intersection(set(['filename', 'length', 'extension', 'bitRate', 'bitDepth']))) >= 4
                except AssertionError:
                    self._log.warning(f"Mismatch - keys missing - {result['filename']}")
                    continue
                # BITRATE
                try:
                    bitrate = result['bitRate'] if 'bitRate' in result.keys() else result['bitDepth'] * 44
                    potential_matches.append((username, result, bitrate))
                except KeyError:
                    self._log.warning(f"Mismatch - bitrate missing - {result['filename']}")
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