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
            # print("DOWNLOAD STAUTS")
            # print(file['state'])
            # print(fname)
            # print(f)
            # print(fname == f)
            # print()

            if completed and (fname == f):
                return file
            else:
                return None
        return

