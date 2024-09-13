from datetime import datetime
import os
import time

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
                file = self.check_download_state(username=username)
                if not file:
                    continue
                elif file['state'] == 'Completed, Succeeded':
                    self._log.info(f"Download complete: {f}")
                    return file, download_attempted_at
                else: 
                    self._log.error(f"Download failed: {f}")
                    return None, download_attempted_at
                time.sleep(1)
        except Exception as e:
            self._log.error(f"Download error: {e}")
            raise


    def check_download_state(self, username):
        # download = self.transfer_api.get(download(self.dl_username, self.dl_file))
        downloads = self.transfer_api.get_all_downloads()
        dl_from_username = [download for download in downloads if download['username'] == username]

        for dl in dl_from_username:
            file = dl['directories'][0]['files'][0]
            completed = 1 if file['state'] == 'Completed, Succeeded' else 0
            fname = file['filename']
            username = file['username']

            if completed:
                return file
            else:
                return None
        return

    def move_file(self, src, dest):
        """Moves the downloaded file to the designated location."""
        try:
            if os.path.exists(dest):
                self._log.info(f"Destination file {dest} already exists. Deleting the source file {src}.")
                os.remove(src)
            else:
                os.rename(src, dest)
                self._log.info(f"Moved file from {src} to {dest}")
        except Exception as e:
            self._log.error(f"Error moving file: {e}")