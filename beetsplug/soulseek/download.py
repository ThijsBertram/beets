from datetime import datetime
import os
import time

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
            self._log.info(f"{CYAN}Download started:{RESET} {YELLOW}{f}{RESET}")        
            while True:
                if time.perf_counter() > timeout:
                    self._log.error(f"Download timeout: {YELLOW}{f}{RESET} after {RED}{self.dl_timeout}{RESET} seconds")
                    return None, download_attempted_at
                # status = self.transfer_api.state(download_id)
                file = self.check_download_state(username=username, f=f)
                if file['state'] == 'InProgress':
                    time.sleep(2)
                    continue
                elif file['state'] == 'Completed, Succeeded':
                    self._log.info(f"{GREEN}Download complete:{RESET} {YELLOW}{f}{RESET}")
                    return file, download_attempted_at
                elif file['state'] == 'Queued, Remotely':
                    self._log.info(f"{RED}Download queued remotely:{RESET} {YELLOW}{f}{RESET}")
                    return file, download_attempted_at
                elif file['state'] == 'Completed, Errored':
                    self._log.info(f"{RED}Download errored:{RESET} {YELLOW}{f}{RESET}")
                    return file, download_attempted_at
                else: 
                    self._log.error(f"{RED}Download failed:{RESET} {YELLOW}{f}{RESET}")
                    return file, download_attempted_at
        except Exception as e:
            self._log.error(f"{RED_BRIGHT}Download error:{e}{RESET}")
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


            if (fname == f):
                return file
