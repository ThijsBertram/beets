from slskd_api.apis import SearchesApi
from collections import deque
from datetime import datetime
import asyncio
import time
from tenacity import retry, stop_after_attempt, wait_fixed, wait_exponential
from pathlib import Path

class Searcher:
    """
    A class to handle searching on Soulseek.

    Attributes:
    client : SlskdClient
        The Soulseek client used to perform searches.
    """

    def __init__(self, client, log, skip_extensions=None):
        self.search_api = client.searches
        self._log = log
        self.cache = {}
        self.semaphore = asyncio.Semaphore(1)  # Ensure only one request at a time
        self.skip_extensions = skip_extensions or ['m4a']

    def create_queries(self, item):
        """Creates search queries from the song dictionary."""
        simple = ' '.join([item[k] for k in ['main_artist', 'feat_artist', 'title', 'remixer', 'remix_type'] if item[k]])
        # simpler = ' '.join([item[k] for k in ['main_artist', 'title', 'remixer'] if item[k]])
        # simplest = ' '.join([item[k] for k in ['main_artist', 'title'] if item[k]])
        # return deque([simple, simpler, simplest])
        return deque([simple])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_soulseek(self, query):
        """Initiates a search on Soulseek with exponential backoff and rate limiting."""
        async with self.semaphore:
            try:
                self._log.log("info", f"Initiating search for query: {query}")
                if query in self.cache:
                    self._log.log("info", f"Using cached results for query: {query}")
                    return self.cache[query]

                search = await self._enqueue_search(query)
                self.cache[query] = search['id']  # Cache the search results
                await asyncio.sleep(10)  # Ensure sufficient throttling
                return search['id']
            except Exception as e:
                self._log.log("error", f"Search error: {e}")
                raise

    async def _enqueue_search(self, query):
        """Enqueue a search and ensure it returns valid async results."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.search_api.search_text, query)

    async def search_finished(self, search_id):
        loop = asyncio.get_event_loop()
        try:
            # self._log.log("info", f"Checking if search ID {search_id} is complete.")
            state = await loop.run_in_executor(None, self.search_api.state, search_id)
            # self._log.log("info", f"Search state for ID {search_id}: {state}")
            return state.get('isComplete', False)
        except Exception as e:
            self._log.log("error", f"Error checking search state: {e}")
            return False


    async def _fetch_search_results(self, search_id):
        """Fetch search results using an executor for sync APIs."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.search_api.search_responses, search_id)

    def filter_results(self, results, item):
        """
        Filters search results based on song metadata.

        Args:
            results (list): List of search results.
            item (dict): Song metadata.

        Returns:
            list: Filtered results.
        """
        filtered = []
        for result_group in results:
            username = result_group.get('username', 'unknown_user')
            for result in result_group.get('files', []):
                extension = result.get('extension')
                if not extension:
                    extension = Path(result['filename']).suffix.lstrip('.')

                if extension and extension.lower() in self.skip_extensions:
                    continue

                if result.get('isLocked'):
                    self._log.log("warning", f"Skipping locked file: {result['filename']} (user: {username})")
                    continue

                if not result.get('bitRate') and not result.get('bitDepth'):
                    self._log.log("warning", f"Skipping file with missing bitrate/bitdepth: {result['filename']} (user: {username})")
                    continue

                filtered.append({
                    'username': username,
                    'file': result
                })

        self._log.log("info", f"Filtered down to {len(filtered)} results for item: {item['title']}")
        return filtered

    def rank_results(self, results, item):
        """
        Ranks search results based on match quality.

        Args:
            results (list): List of filtered results.
            item (dict): Song metadata.

        Returns:
            list: Ranked results.
        """
        for result in results:
            file_data = result['file']
            if 'bitDepth' in file_data and 'bitRate' not in file_data:
                file_data['bitRate'] = file_data['bitDepth'] * 44  # Approximate conversion

        ranked = sorted(results, key=lambda x: x['file'].get('bitRate', 0), reverse=True)
        self._log.log("info", f"Ranked {len(ranked)} results for item: {item['title']}")
        return ranked

    async def perform_search(self, item):
        queries = self.create_queries(item)
        results = []

        for query in queries:
            try:
                self._log.log("info", f"Attempting search for query: {query}")
                search_id = await self.search_soulseek(query)
                # self._log.log("info", f"Search initiated with ID: {search_id}")
                
                if search_id:
                    while not await self.search_finished(search_id):
                        time.sleep(1)
                    raw_results = await self.get_search_results(search_id)
                    self._log.log("info", f"Raw results fetched for query: {query}")

                    filtered_results = self.filter_results(raw_results, item)
                    ranked_results = self.rank_results(filtered_results, item)

                    if ranked_results:
                        results.extend(ranked_results)
            except Exception as e:
                self._log.log("error", f"Error during search for query '{query}': {e}")

        return results


    def match_results(self, search_results, item):
        """
        Matches search results to the song.

        Args:
            search_results (list): List of search results.
            item (dict): Song metadata.

        Returns:
            list: Best matching results.
        """
        matches = []

        for result in search_results:
            file_data = result['file']
            if item['main_artist'].lower() in file_data['filename'].lower() and item['title'].lower() in file_data['filename'].lower():
                matches.append(result)

        if item.get('remixer'):
            matches = [m for m in matches if item['remixer'].lower() in m['file']['filename'].lower()]

        if item.get('feat_artist'):
            matches = [m for m in matches if item['feat_artist'].lower() in m['file']['filename'].lower()]

        self._log.log("info", f"Matched {len(matches)} results for item: {item['title']} after filtering.")
        return matches

    async def get_search_results(self, search_id):
        """Retrieves search results from Soulseek."""
        try:
            results = self.search_api.search_responses(search_id)
            return results
        except Exception as e:
            self._log.error(f"Get search results error: {e}")
            return []