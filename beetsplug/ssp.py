from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets import config
from openai import OpenAI
import sqlite3
import time
import json
import os
import re


class OpenAICaller:
    def __init__(self, api_key, assistant_id):
        """
        Args:
            api_key (str): key for Open ai. ideally grabbed from env as OPENAI_API_KEY
            assistant_id (str): id of the assistant to pass the request to
        """
        self.client = OpenAI(api_key=api_key)
        self.assistant_id = assistant_id

    def _create_thread(self):
        """ Create a thread

        Returns:
            Thread: A new/fresh OpenAI thread object to use for parsing a song string
        """
        return self.client.beta.threads.create()
    
    def _submit_message(self, t, p):
        """ Post a prompt p to a thread t

        Args:
            t (thread object): OpenAI thread object, create with the function self._create_thread
            p (string): prompt to send to the assistant 

        Returns:
            OpenAI run object: Run object
        """
        self.client.beta.threads.messages.create(thread_id=t.id, role="user", content=p)
        return self.client.beta.threads.runs.create(thread_id=t.id, assistant_id=self.assistant_id)

    def _wait_for_response(self, thread, run):
        """ Wait for an OpenAI run to finish so we can extract data from the response

        Args:
            run (Run): The run we want to wait for

        Returns:
            Run: the finished run
        """
        while run.status == "queued" or run.status == "in_progress":
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id,
            )
            time.sleep(0.5)
        return run

    def _get_messages(self, thread):
        """ Get all messages for a given thread

        Args:
            tread (Thread): OpenAI Thread object for which to fetch all messages

        Returns:
            list: list of all messages within the thread
        """
        return json.loads(self.client.beta.threads.messages.list(thread_id=thread.id, order="asc").to_json())['data']
    
    def _parse_response(self, messages):
        """ Get last message from a thread and parse the content of that message so we can return a dictionary containing song_data

        Args:
            thread (Thread): OpenAI thread object to retreive the last message from
        """
        last_message = messages[-1]['content']
        answer = last_message[0]['text']['value']
        data = eval(answer)
        return data

    def parse_song_string(self, song_string):
        """ Use an OpenAI assistant to parse a song string and extract data from it.
                1. Create a thread
                2. Submit a message to the thread and run the thread
                3. Wait for a response
                4. Get messages in thread from response
                4. Get last message and parse it to return a dictionary of song data
        Args:
            song_string (str): String representing a song 

        Returns:
            dict: Dictionary containing song data (keys match beets database columns)
        """
        thread = self._create_thread()
        run = self._submit_message(thread, song_string)
        run = self._wait_for_response(thread, run)
        messages = self._get_messages(thread)
        song_data = self._parse_response(messages)
        return song_data
   
class SongStringParser(BeetsPlugin):
    def __init__(self):
        super(SongStringParser, self).__init__()

        # Load configuration
        self.config.add({
            'api_key': '',
            'assistant_id': ''
        })

        try:
            api_key = self.config['api_key'].get(str)
            assistant_id = self.config['assistant_id'].get(str)
        except config.ConfigValueError as e:
            self._log.error('Configuration error: %s', e)
            return

        self.parser = OpenAICaller(api_key, assistant_id)

        # Define a custom command for Beets
        self.custom_gpt_command = Subcommand('ssp', help='Send request to OpenAI GPT')
        self.custom_gpt_command.func = self.send_gpt_request

        self.known_artists = self.get_known_artists_from_db()


    def get_known_artists_from_db(extract_duos_only=True):
        # Connect to the SQLite database (change the connection method for other databases)
        database_path = str(config['library'])
        table_name = 'items'

        conn = sqlite3.connect(database_path)
        cursor = conn.cursor()
        
        # Query to get all rows in the 'artists' column
        query = f"SELECT artists FROM {table_name}"
        cursor.execute(query)
        
        # Set to store all unique artists
        known_artists = set()

        # Fetch all rows from the artists column
        rows = cursor.fetchall()

        # Iterate over each row (each row contains a single column 'artists')
        for row in rows:
            # Assume artists are separated by commas or the special string "\\␀"
            artists_string = row[0]  # Extract the artists string from the tuple
            
            # Split the artists string by commas and the special string "\\␀"
            try:
                artists_list = re.split(r',|\\␀', artists_string)
            except TypeError:
                continue
            # Strip whitespace and process each artist
            for artist in artists_list:
                artist = artist.strip()
                if extract_duos_only:
                    # Only add if the artist contains an '&' (artist duo)
                    if '&' in artist:
                        known_artists.add(artist)
                else:
                    # Add all artists
                    known_artists.add(artist)
        
        # Close the database connection
        conn.close()
        
        return list(known_artists)

    def commands(self):
        return [self.custom_gpt_command]
    
    def extract_simple_ss(self, song_string):

        forbidden_characters = ['|']

        for char in forbidden_characters:
            if char in song_string:
                return None

        known_duos = self.known_artists
        # Normalize known duos to lowercase for case-insensitive matching
        known_duos_lower = [duo.lower() for duo in known_duos]

        # Step 1: Check for the delimiter " - "
        delimiter = " - "

        if delimiter not in song_string:
            # If no delimiter, try to find the title part in double quotes
            match = re.search(r'"(.*?)"$', song_string)  # Match title in double quotes at the end
            if not match:
                return None  # Too complex if no delimiter or double quotes found
            
            # Extract title and artist
            title = match.group(1).strip()  # Title inside double quotes
            artist = song_string.replace(f'"{title}"', '').strip()  # Everything before the title
        else:
            if song_string.count(delimiter) != 1:
                return None  # Too complex if no or more than 1 delimiter
            # If delimiter is present, split using " - "
            artist, title = song_string.split(delimiter)
            artist = artist.strip()
            title = title.strip()

        
        # Step 2: Detect and process information between brackets
        bracket_pattern = r"\((.*?)\)|\[(.*?)\]|\{(.*?)\}"
        bracket_matches = re.findall(bracket_pattern, song_string)
        
        remix_patterns = ['remix', 'mix', 'rmx', 'edit', 'rework', 'version', 'bootleg', 're-edit', 
                        'dub', 'extended mix', 'radio edit', 'club mix', 'VIP mix', 'bootleg mix', 
                        'mashup', 'refix', 'interpretation', 'remake', 'remodel', 'remaster']
        
        feature_patterns = ['feat.', 'featured', 'featuring', 'ft.']
        
        remove_patterns = ['Original Video', 'Original Mix', 'Original', 'Official Video', 'Videoclip']
        
        remix_mapping = {
            'remix': 'remix', 'rmx': 'remix', 'rework': 'remix', 'refix': 'remix', 
            'interpretation': 'remix', 'remake': 'remix', 'remodel': 'remix', 
            're-edit': 'remix', 'mix': 'remix', 'extended mix': 'remix', 'dub': 'dub', 
            'radio edit': 'dub', 'club mix': 'dub', 'bootleg': 'bootleg', 'bootleg mix': 'bootleg',
            'version': 'edit', 'remaster': 'remaster', 'edit': 'edit'  # Adding 'version' to the mapping
        }

        # To hold processed information
        remix_info = None
        feature_info = None
        
        # Process each substring inside brackets
        for match in bracket_matches:
            content = next(filter(None, match))  # Extract content
            
            # Case-insensitive matching by converting content to lowercase
            content_lower = content.lower()

            # Check if it's a remix or feature
            if any(pattern in content_lower for pattern in remix_patterns):
                remix_type = next(remix_mapping[pattern] for pattern in remix_patterns if pattern in content_lower)
                # # Remove the remix indicators from the content to get the remix artist
                # remix_artist = re.sub(r'(?i)(' + '|'.join(remix_patterns) + ')', '', content, flags=re.IGNORECASE).strip()
                
                # # Further clean remix_artist by removing any additional words that are purely remix-related terms
                # remix_artist = remix_artist.split()  # Split into words
                # remix_artist = ' '.join([word for word in remix_artist if word.lower() not in remix_patterns]).strip()
                # Find the exact remix indicator (case-insensitive) to remove from the content
                for pattern in remix_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        original_remix_indicator = pattern
                        break

                # Remove the original remix indicator from the content to get the remix artist
                if original_remix_indicator:
                    remix_artist = re.sub(f'(?i){original_remix_indicator}', '', content, flags=re.IGNORECASE).strip()
                else:
                    remix_artist = content.strip()    


                # If remix_artist is empty after stripping, set to None
                remix_artist = remix_artist if remix_artist else ''
                
                remix_info = (remix_artist, remix_type)
            
            elif any(pattern in content_lower for pattern in feature_patterns):
                feature_artist = re.sub(r'(?i)(' + '|'.join(feature_patterns) + ')', '', content).strip()
                feature_info = feature_artist
            
            # Check if the content matches any remove_patterns
            elif any(pattern.lower() in content_lower for pattern in remove_patterns):
                # Remove this content and continue processing
                song_string = re.sub(re.escape(content), '', song_string)
                continue  # Skip this bracket content and continue
            else:
                return None  # Complex substring found
        
        # Step 3: Clean the original string by removing the brackets
        cleaned_song_string = re.sub(bracket_pattern, '', song_string).strip()

        # # Step 4: Split into artist and title
        # artist, title = cleaned_song_string.split(delimiter)
        # artist = artist.strip()
        # title = title.strip()
        artist = re.sub(bracket_pattern, '', artist).strip()
        title = re.sub(bracket_pattern, '', title).strip()
        
        # Step 5: Process artist part
        def process_artists(artist_string):
            # Split on commas first, since artists separated by commas should always be split
            artist_list = [a.strip() for a in artist_string.split(',')]
            
            final_artists = []
            
            for artist in artist_list:
                # Check for '&' and handle artist duos case-insensitively
                if '&' in artist:
                    # Normalize artist to lowercase for comparison
                    normalized_artist = artist.lower()
                    # If it's a known duo (case-insensitive), keep it together
                    if normalized_artist in known_duos_lower:
                        final_artists.append(artist)  # Add the original artist
                    else:
                        # Otherwise, split it on '&' and add both artists separately
                        duo_artists = [a.strip() for a in artist.split('&')]
                        final_artists.extend(duo_artists)
                else:
                    # No '&' present, add as is
                    final_artists.append(artist)
            
            return final_artists
        
        # Step 6: Apply the artist processing logic
        artists = process_artists(artist)

        remix_artist, remix_type = remix_info if remix_info else ('', '')

        return {
            'artists': artists,  # List of artists
            'title': title,
            'remix_type': remix_type,  # (remix_artist, remix_type) or None
            'remixer': remix_artist,
            'feat_artist': feature_info if feature_info else ''  # featured_artist or None
        }

    def send_gpt_request(self, args):
        results = list()
        for song_string in args:
            try:
                response = self.parser.parse_song_string(song_string)
                # print(response)
                self._log.info(f'CHATGPT CORRECTLY PARSED Song String: {song_string}\n\n')
                results.append((song_string, response))
            except Exception as e:
                self._log.error(f"Error processing song string {song_string}: {e}")

        return results

    def concat_artists(self, string_list):
        if len(string_list) == 0:
            return ""
        elif len(string_list) == 1:
            return string_list[0]
        elif len(string_list) == 2:
            return ' & '.join(string_list)
        else:
            return ', '.join(string_list[:-1]) + ' & ' + string_list[-1]
        
    def string_from_item(self, item, ext=None, path=None):
        
        artists = item['artists'][0].split(",") ### ?????????????????????????????????
        feat_artist = item['feat_artist']
        remixer = item['remixer']
        remix_type = item['remix_type']
        main_artist = item['main_artist']
        # get unique collab_artists
        special_artists = set([feat_artist]).union(set([remixer])).union(set([main_artist]))
        collab_artists = list(set(artists) - special_artists)
        artists = [main_artist] + collab_artists
        # artist part
        artist_part = self.concat_artists(artists)
        if feat_artist:
            artist_part += f' feat. {feat_artist}'
        # title part
        title_part = item['title']
        if remixer:
            title_part += f' ({remixer} {remix_type})'
        # string
        s = f'{artist_part} - {title_part}'

        # extension
        if ext:
            s += f'.{ext}'
        # path
        if path:
            s = os.path.join(path, s)
        
        return s