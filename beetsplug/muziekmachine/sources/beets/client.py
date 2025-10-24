from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping, Optional

from beetsplug.muziekmachine.sources.base import SourceClient, RetryPolicy
from beetsplug.muziekmachine.sources.base.errors import (
    ClientConfigError, ClientNotFoundError, ClientCapabilityError
)

from beets.library import Library, Item
from beets.dbcore import Query
from beets.util import bytestring_path
from pathlib import Path
import sqlite3


from beetsplug.muziekmachine.domain.models import SourceRef, PlaylistRef
from beetsplug.muziekmachine.domain.diffs import Diff


# TODO: MOVE TO CONFIG
BEETS_CAPABILITIES = {
            "title", "artist", "album", "albumartist", "genre",
            "bpm", "key", "comments", "path",
        }



class BeetsClient(SourceClient):
    
    source = 'beets' 

    def __init__(self, *, lib, retry_policy: Optional[RetryPolicy] = None) -> None:
        super().__init__(retry_policy=retry_policy)
        self.lib = lib
        self.db = lib._db

    # lifecycle (mostly no-op)
    def connect(self) -> None:
        if self.lib is None:
            raise ClientConfigError("BeetsClient requires a beets Library instance.")    

    def close(self) -> None:
        return
    
    def capabilities(self) -> set[str]:
        # You can safely write many fields; keep this explicit and adjustable.
        return BEETS_CAPABILITIES
    
    def iter_items(self) -> Iterable[Item]:
        yield from self.lib.items()

    def get_item(self, ref: SourceRef, **kwargs) -> Item:

        if ref.source != 'beets':
            raise ClientConfigError("BeetsClient.get_item requires SourceRef(source='beets').")
    
        if ref.external_id:
            item = self.lib.get_item(int(ref.external_id))

            if not item:
                raise ClientNotFoundError(f'Beets item id={ref.external_id} not found')
            return item
        
        if ref.path:
            return self.lib.get_item(bytestring_path(ref.path))
        
        raise ClientConfigError('Beets SourceRef must contain id or path')
    
    def apply(self, ref: SourceRef, diff: Diff) -> None:

        item = self.get_item(ref)
        changes = diff.changes

        new_path = None
        if 'path' in changes:
            _, new_path = changes['path']
        
        for field, (_old, new) in changes.items():
            if field == 'path':
                continue
            setattr(item, field, new)

        item.store()
        item.write()

        if new_path:
            item.move(write=True)

        return

    def iter_collections(self, **kwargs) -> Iterable[Dict[str, Any]]:
        cur = self._db._connectoin().execute('SELECT * FROM playlists ORDER BY name ASC')
        cols = [d[0] for d in cur.description]

        for row in cur.fetchall():
            yield dict(zip(cols, row))
        
    def get_collection(self, ref: PlaylistRef, **kwargs) -> Dict[str, Any]:
        if ref.source != 'beets' or not ref.playlist_id:
            raise ClientConfigError("Beets get_collection requires PlaylistRef(source='beets', id=<id>)")
    
        cur = self._db._connection().execute('SELECT * FROM playlists WHERE id=?', (ref.playlist_id))
        row = cur.fetchone()

        if not row:
            raise ClientNotFoundError(f"Beets playlist id={ref.playlist_id} not found")

        cols = [d[0] for d in cur.description]

        return dict(zip(cols, row))

    def iter_collections(self):
# Your schema: playlists(id, name, description, spotify_id, soundcloud_id, youtube_id, rekordbox_id, path, last_edited_at, type)
        rows = self.db._connection.execute("SELECT id, name, description, type, last_edited_at FROM playlists")
        for row in rows:
            yield {
                "playlist_id": row["id"],
                "playlist_name": row["name"],
                "playlist_description": row["description"],
                "type": row["type"],
                "last_edited_at": row["last_edited_at"],
            }


        return
    
    def iter_items_in_collection(self, playlist_row: Mapping[str, Any], **kwargs) -> Iterable[Item]:
        playlist_id = playlist_row['playlist_id']

        sql = '''
        SELECT i.* from items i
        JOIN playlist_item pi on pi.item_id = i.id
        WHERE pi.playlist_id = ?
        ORDER BY pi.position ASC
        '''

        for it in self.lib._db.query(sql, (playlist_id,)):
            yield self.lib.get_item(it['id'])




    # ==================
    # CRUD PLAYLISTS
    # ==================
    

    #     # --- playlist field updates
    # def update_playlist_fields(self, pref: PlaylistRef, field_changes: Dict[str, tuple]) -> None:
    #     """Apply name/description/... field changes to playlists table."""
    #     if not field_changes:
    #         return
    #     set_clause = []
    #     params = []
    #     for field, (old, new) in field_changes.items():
    #         set_clause.append(f"{field} = ?")
    #         params.append(new)
    #     params.append(pref.id)
    #     sql = f"UPDATE playlists SET {', '.join(set_clause)} WHERE id=?"
    #     self._db._connection().execute(sql, params)
    #     self._db._connection().commit()

    # # --- playlist membership ops
    # def add_members(self, pref: PlaylistRef, item_ids: List[int], position: Optional[int] = None) -> None:
    #     conn = self._db._connection()
    #     # determine starting position (append if None)
    #     if position is None:
    #         cur = conn.execute("SELECT COALESCE(MAX(position), -1) FROM playlist_item WHERE playlist_id=?", (pref.id,))
    #         start = (cur.fetchone()[0] or -1) + 1
    #     else:
    #         start = position
    #         # shift positions >= position
    #         conn.execute("""
    #             UPDATE playlist_item SET position = position + ?
    #             WHERE playlist_id=? AND position >= ?
    #         """, (len(item_ids), pref.id, position))
    #     # insert items
    #     for idx, iid in enumerate(item_ids):
    #         conn.execute(
    #             "INSERT OR IGNORE INTO playlist_item(playlist_id,item_id,position) VALUES(?,?,?)",
    #             (pref.id, iid, start + idx)
    #         )
    #     conn.commit()

    # def remove_members(self, pref: PlaylistRef, item_ids: List[int]) -> None:
    #     conn = self._db._connection()
    #     for iid in item_ids:
    #         conn.execute("DELETE FROM playlist_item WHERE playlist_id=? AND item_id=?", (pref.id, iid))
    #     conn.commit()

    # def move_member(self, pref: PlaylistRef, item_id: int, to_index: int) -> None:
    #     """Simple move: reassign one item's position; compact positions if desired."""
    #     conn = self._db._connection()
    #     # naive approach: set to target index, then renumber densely
    #     conn.execute("UPDATE playlist_item SET position=? WHERE playlist_id=? AND item_id=?", (to_index, pref.id, item_id))
    #     # optional: renumber to 0..n-1 by current order
    #     rows = conn.execute("SELECT item_id FROM playlist_item WHERE playlist_id=? ORDER BY position ASC", (pref.id,)).fetchall()
    #     for pos, (iid,) in enumerate(rows):
    #         conn.execute("UPDATE playlist_item SET position=? WHERE playlist_id=? AND item_id=?", (pos, pref.id, iid))
    #     conn.commit()

    # # optional create/delete playlists
    # def create_playlist(self, name: str, description: str | None = None, type_: str | None = None) -> PlaylistRef:
    #     conn = self._db._connection()
    #     cur = conn.execute(
    #         "INSERT INTO playlists(name, description, type) VALUES (?, ?, ?)",
    #         (name, description or "", type_ or "manual")
    #     )
    #     conn.commit()
    #     pid = cur.lastrowid
    #     return PlaylistRef(source="beets", id=str(pid))

    # def delete_playlist(self, pref: PlaylistRef) -> None:
    #     conn = self._db._connection()
    #     conn.execute("DELETE FROM playlist_item WHERE playlist_id=?", (pref.id,))
    #     conn.execute("DELETE FROM playlists WHERE id=?", (pref.id,))
    #     conn.commit()