import os

from beetsplug.ssp import SongStringParser


song_dir = os.path.abspath('D:\SOULSEEK\slskd\src\downloads - kopie')
files = [song for song in os.listdir(song_dir) if not song.endswith('.py')]


ssp = SongStringParser()



for f in files:

    old_fp = os.path.join(song_dir, f)
    f, ext = os.path.splitext(f)

    print(f)


    info = ssp.extract_info(f)

    artists = info.pop('artists')
    # remove duplicates and substrings
    if not artists:
        print("ERROROROROROR")
        continue

    # Remove duplicates based on substrings
    substrings = {a for a in artists for other in artists if a != other and a in other}
    artists = [a for a in artists if a not in substrings]
    main_artist = artists[0]
    # sort
    artists = sorted(artists)


    info['artists'] = artists
    info['main_artist'] = main_artist



    try:
        new_fp = ssp.item_to_string(info, ext=ext, path=song_dir)

        new_fp = new_fp.replace('..', '.')
    except Exception as e:
        print(f"Error: {e}")
        print("TUNRE :", f)
        print()
    try:

        os.rename(old_fp, new_fp)
    except FileExistsError:
        os.remove(old_fp)