from beets.library import Library, Item
from beetsplug.ssp import SongStringParser
from beets import config
from beets.dbcore.query import AndQuery, RegexpQuery, OrQuery, SubstringQuery
import re 
import shutil
import os

library_path = 'D:/Muziek/AUDIOFILES'
sqlite_path = 'F:/PROGRAMMING/beets - fork/beets.db'
to_add = 'D:/Muziek/AUDIOFILES/TO ADD'
# Initialize the Library object
lib = Library(path=sqlite_path, 
              directory=library_path)

# Get all items in the library
items = lib.items()
ssp = SongStringParser()

audiofiles = os.listdir(to_add)

for audiofile in audiofiles:

    f, ext = os.path.splitext(audiofile)


    

    info = ssp.extract_info(audiofile)

    main_artist = info['main_artist']
    title, ext = os.path.splitext(info.pop('title'))
    remix_type = info.get('remix_type', '')
    remixer = info.get('remixer', '')

    info['title'] = title.strip()

    title_query = RegexpQuery('title', f'(?i){re.escape(title.strip())}')

    artist_query1 = RegexpQuery('artists', f'(?i){re.escape(main_artist)}')
    artist_query2 = RegexpQuery('artists', f'(?i){re.escape(remixer)}')
    artist_query = OrQuery([artist_query1, artist_query2])

    total_query = AndQuery([title_query, artist_query])


    item = lib.items(total_query).get()

    if item:    

        print(ssp.item_to_string(item))
    else:
        print(f"{main_artist} - {title}")

    new_path = os.path.abspath(ssp.item_to_string(info, ext=ext, path=library_path))
    old_path = os.path.abspath(os.path.join(to_add, audiofile))

    c_new = 0
    c_total = 0

    if item:
        
        shutil.move(old_path, new_path)
        item.path = new_path
        item.store()

        print(f"Moved EXISTING {audiofile} to {new_path}")

    else:

        # DATA 
        # artists
        artists = info.pop('artists')
        substrings = {a for a in artists for other in artists if a != other and a in other}
        artists = [a for a in artists if a not in substrings]
        main_artist = artists[0]
        artists = sorted(artists)
        info['artists'] = artists



        new_item = Item(**info)
        lib.add(new_item)
        new_item.store()

        shutil.move(old_path, new_path)

        print(f"Moved NEW {audiofile} to {new_path}")
        c_new += 1
    c_total += 1
    print()
    # info = ssp.extract_info(audiofile)

                # title = song['title']
                # remixer = song.get('remixer', '')
                # artist = song.get('main_artist', '')
                # feat_artist = song.get('feat_artist', '')
                
                # t = RegexpQuery('title', f'(?i){re.escape(title)}')  # Case-insensitive title match
                # a = RegexpQuery('artist', f'(?i){re.escape(artist)}')  # Case-insensitive artists match
                # main_a = RegexpQuery('main_artist', f'(?i){re.escape(artist)}')
                # r = RegexpQuery('remixer', f'(?i){re.escape(remixer)}') if remixer else None
                # f = RegexpQuery('feat_artist', f'(?i){re.escape(feat_artist)}') if feat_artist else None

                # artist_q = OrQuery([a, main_a])
                # queries = [t, artist_q]    
                # queries += [r] if remixer else []
                # queries += [f] if feat_artist else []

                # c = AndQuery(queries)
                # items = lib.items(c)
                # item = items[0]

print(f"Total: {c_total}")
print(f"New: {c_new}")