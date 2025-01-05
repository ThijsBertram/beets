from datetime import datetime
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

# class Downloader:
#     """
#     A class to handle downloading on Soulseek, including retry logic and error handling.
#     """

#     def __init__(self, client, log, semaphore, timeout, max_retries=3):
#         self.transfer_api = client.transfers
#         self._log = log
#         self.semaphore = semaphore
#         self.dl_timeout = timeout
#         self.max_retries = max_retries

#     @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
#     async def download(self, match, username):
#         """
#         Attempts to download a matched file from Soulseek with retry logic and rate limiting.

#         Args:
#             match (dict): File match information.
#             username (str): The username providing the file.

#         Returns:
#             dict or None: Download file metadata if successful, None otherwise.
#         """
#         async with self.semaphore:
#             for attempt in range(1, self.max_retries + 1):
#                 self._log.log("info", f"Attempt {attempt}/{self.max_retries}: Downloading {match['filename']}")

#                 try:
#                     file, download_attempted_at = await self._attempt_single_download(match, username)

#                     if file and file['state'] == 'Completed, Succeeded':
#                         self._log.log("info", f"Download successful: {match['filename']}")
#                         return file

#                     if file and file['state'] in ['Queued, Remotely', 'Completed, Errored']:
#                         self._log.log("warning", f"Recoverable error state: {file['state']} for {match['filename']}. Retrying...")
#                         await self._delete_queued_download(file)
#                         continue

#                     self._log.log("warning", f"Download failed: {match['filename']}. Retrying...")
#                 except Exception as e:
#                     self._log.log("error", f"Exception during download: {e}")

#             self._log.log("error", f"All retries failed for: {match['filename']}")
#             return None

#     async def _attempt_single_download(self, match, username):
#         """
#         Attempts a single download and checks its state.

#         Args:
#             match (dict): File match information.
#             username (str): The username providing the file.

#         Returns:
#             tuple: (file metadata, download attempted timestamp)
#         """
#         timeout = asyncio.get_event_loop().time() + self.dl_timeout
#         download_attempted_at = datetime.now()

#         try:
#             loop = asyncio.get_event_loop()
#             download = await loop.run_in_executor(None, self.transfer_api.enqueue, username, [match])
#             filename = match['filename'].split('\\')[-1]
#             self._log.log("info", f"Download started: {filename}")

#             while True:
#                 if asyncio.get_event_loop().time() > timeout:
#                     self._log.log("error", f"Download timeout: {filename} after {self.dl_timeout} seconds")
#                     return None, download_attempted_at

#                 file = await self.check_download_state(username, filename)

#                 if file['state'] == 'InProgress':
#                     await asyncio.sleep(2)
#                     continue

#                 if file['state'] == 'Completed, Succeeded':
#                     return file, download_attempted_at

#                 if file['state'] in ['Queued, Remotely', 'Completed, Errored']:
#                     return file, download_attempted_at

#                 self._log.log("warning", f"Download error state: {file['state']} for {filename}")
#                 return file, download_attempted_at

#         except Exception as e:
#             self._log.log("error", f"Exception during download: {e}")
#             return None, download_attempted_at

#     async def check_download_state(self, username, filename):
#         """
#         Checks the state of a download for a specific file and username.

#         Args:
#             username (str): The username providing the file.
#             filename (str): The file being downloaded.

#         Returns:
#             dict: File metadata containing state and other details.
#         """
#         loop = asyncio.get_event_loop()
#         downloads = await loop.run_in_executor(None, self.transfer_api.get_all_downloads)
#         user_downloads = [dl for dl in downloads if dl['username'] == username]

#         for dl in user_downloads:
#             file = dl['directories'][0]['files'][0]
#             fname = file['filename'].split('\\')[-1]

#             if fname == filename:
#                 return file

#         return {'state': 'Unknown'}

#     async def _delete_queued_download(self, file):
#         """
#         Deletes a download that is in a queued state.

#         Args:
#             file (dict): The file metadata to delete.
#         """
#         try:
#             loop = asyncio.get_event_loop()
#             await loop.run_in_executor(None, self.transfer_api.remove, file['id'])
#             self._log.log("info", f"Deleted queued download: {file['filename']}")
#         except Exception as e:
#             self._log.log("warning", f"Failed to delete queued download: {file['filename']}. Error: {e}")









class Downloader:
    """
    A class to handle downloading on Soulseek, including retry logic and error handling.
    """

    def __init__(self, client, log, semaphore, timeout, max_retries=1):
        self.transfer_api = client.transfers
        self._log = log
        self.semaphore = semaphore
        self.dl_timeout = timeout
        self.max_retries = max_retries

    async def download(self, match, username):
        """
        Attempts to download a matched file from Soulseek with sequential retry logic.

        Args:
            match (dict): File match information.
            username (str): The username providing the file.

        Returns:
            dict or None: Download file metadata if successful, None otherwise.
        """
        async with self.semaphore:
            self._log.log("info", f"Starting download for {match['filename']}")

            try:
                file, download_attempted_at = await self._attempt_single_download(match, username)

                if file and file['state'] == 'Completed, Succeeded':
                    self._log.log("info", f"Download successful: {match['filename']}")
                    return file
                else:
                    self._log.log("warning", f"Final state after download attempt: {file['state']} for {match['filename']}")
                    return file

            except Exception as e:
                self._log.log("error", f"Exception during download: {e}")
                return {'state': 'Unknown'}

    async def _attempt_single_download(self, match, username):
        """
        Attempts a single download and checks its state.

        Args:
            match (dict): File match information.
            username (str): The username providing the file.

        Returns:
            tuple: (file metadata, download attempted timestamp)
        """
        timeout = asyncio.get_event_loop().time() + self.dl_timeout
        download_attempted_at = datetime.now()

        try:
            self._log.log("info", f"Enqueuing download for {match['filename']}")
            self.transfer_api.enqueue(username, [match])

            filename = match['filename'].split('\\')[-1]
            self._log.log("info", f"Download enqueued: {filename}")

            while True:
                if asyncio.get_event_loop().time() > timeout:
                    self._log.log("error", f"Download timeout: {filename} after {self.dl_timeout} seconds")
                    return file, download_attempted_at

                await asyncio.sleep(2)  # Allow sufficient time for state updates

                file = await self.check_download_state(username, filename)
                if file and file['state'] == 'Completed, Succeeded':
                    self._log.log("info", f"Download completed successfully: {filename}")
                    return file, download_attempted_at

                if file and file['state'] == 'InProgress':
                    self._log.log("info", f"Download in progress for: {filename}")
                    continue

                if file and file['state'] in ['Queued, Remotely', 'Completed, Errored']:
                    self._log.log("warning", f"Recoverable state: {file['state']} for {filename}")
                    return file, download_attempted_at

                self._log.log("error", f"Unexpected state: {file['state']} for {filename}")
                return {'state': 'Unknown'}, download_attempted_at

        except Exception as e:
            self._log.log("error", f"Exception during download: {e}")
            return None, download_attempted_at

    async def _delete_queued_download(self, file):
        """
        Deletes a download that is in a queued state.

        Args:
            file (dict): The file metadata to delete.
        """
        try:
            if hasattr(self.transfer_api, "remove"):
                self.transfer_api.remove(file['id'])
                self._log.log("info", f"Deleted queued download: {file['filename']}")
            else:
                self._log.log("error", "The transfer API does not support the 'remove' method.")
        except Exception as e:
            self._log.log("warning", f"Failed to delete queued download: {file['filename']}. Error: {e}")


    async def check_download_state(self, username, filename):
        """
        Checks the state of a download for a specific file and username.

        Args:
            username (str): The username providing the file.
            filename (str): The file being downloaded.

        Returns:
            dict: File metadata containing state and other details.
        """
        downloads = await asyncio.get_event_loop().run_in_executor(None, self.transfer_api.get_all_downloads)
        user_downloads = [dl for dl in downloads if dl['username'] == username]

        for dl in user_downloads:
            file = dl['directories'][0]['files'][0]
            fname = file['filename'].split('\\')[-1]

            if fname == filename:
                return file

        self._log.log("warning", f"File {filename} not found in user downloads.")
        return {'state': 'Unknown'}