# muziekmachine status review (initial architecture + roadmap)

This document summarizes the current state of `beetsplug/muziekmachine` and a proposal to get to a robust multi-source sync plugin.

## 1) Current architecture (what already exists)

## Plugin layer
- `MuziekMachine` is the orchestrator plugin and currently exposes one command (`mm-pull`) with a `--platform` selector.
- It composes sub-plugins for Spotify, Beets, and YouTube.

## Source abstraction layer
There is a strong architectural start around a generic source interface:
- `SourceClient` (transport/I/O contract): lifecycle (`connect`, `close`), listing collections, iterating items, fetching item, and applying diffs.
- `SourceAdapter` (projection contract): map raw objects to canonical `SongData`, render `current` and `desired` maps for diffing, create a stable `SourceRef`, and expose capabilities.
- `PlaylistAdapter` (playlist contract): identity, mapping to `PlaylistData`, field/member projection, and playlist diff helpers.

This split is good and gives a clean boundary between API clients, canonical models, and sync logic.

## Domain layer
- `SongData`, `SourceRef`, `PlaylistData`, `PlaylistRef`, `SongPointer`, and `CollectionStub` are present.
- `playlist_diffs.py` implements usable field and membership diff logic.

## Services layer
- `ingestion.pull_source()` implements source-agnostic ingestion for songs.
- `playlist_ingestion` provides collection filtering and playlist ingestion from stubs.

## Implemented source adapters/clients
- Spotify source: client + adapter + mapper + playlist adapter/mapper + CLI plugin (`sf-pull-songs`, `sf-pull-playlist`).
- YouTube source: client + adapter + mapper + playlist adapter/mapper + CLI plugin (`yt-pull-songs`, `yt-pull-playlist`).
- Beets source: client + adapter + mapper + playlist adapter/mapper + CLI plugin (`beets-pull`, `beets-pull-playlist`).

## Soulseek
- A separate Soulseek plugin (`SoulSeekPlugin`) with async search/download logic exists and appears more mature than the sync domain layer.

## 2) Main gaps and technical risks

## 2.1 Orchestrator/plugin integration gaps
- `MuziekMachine._cmd_pull_spotify` currently `quit()`s early, so orchestration is not functional.
- `sources` registry only includes Spotify under `all`, while `--platform` claims more sources.
- Raises string exceptions (`raise 'not a valid platform'`), which is invalid Python exception style.

## 2.2 Domain model inconsistencies
- `SongData` is missing fields used by mappers (e.g., Spotify mapper uses `feat_artist`).
- Field naming is inconsistent across layers (`path` vs `audiofile_path`, `comments` vs `comment`, etc.).
- `SourceRef` uses `external_id`, but some clients use `ref.id`.
- Several classmethods in `SongData` are stubs.

## 2.3 Sync core missing
- `domain/diffs.py` is a placeholder, while `SourceAdapter.compute_diff()` depends on it.
- `domain/matching.py`, `merging.py`, `normalization.py` are empty.
- `services/sync.py`, `services/clean.py`, `services/ssp.py` are empty placeholders.

## 2.4 Playlist layer partially implemented
- `playlist_diffs` has duplicate `compute_field_diff` definitions.
- Playlist adapters exist, but write/apply operations are not implemented in clients.
- Membership reconciliation to canonical song ids is not implemented.

## 2.5 Source implementation issues
- Spotify and YouTube clients use `ref.id` in `get_item`; should use `ref.external_id`.
- Beets plugin call path has an argument mismatch in `_make_client_adapter` usage.
- Rekordbox source package exists but is empty.
- Filesystem, SoundCloud, and string source modules do not exist yet (despite being part of target vision).

## 2.6 beets integration concerns
- Sub-plugins are instantiated inside a plugin; this is uncommon for beets and can be simplified by exposing one plugin with multiple subcommands.
- No tests currently validate plugin command registration, mapping correctness, or sync behavior.

## 3) Alignment with beets plugin model (quick check)

The code follows the essential beets plugin primitives:
- subclasses of `BeetsPlugin`,
- `commands()` returning `Subcommand` instances,
- subcommand handlers with signature `(lib, opts, args)`.

This is the correct base. The main work is in internal consistency, orchestration, and implementation completeness.

## 4) Proposed roadmap to meet your requirements

## Phase 0 — Stabilize foundations (must-do first)
1. **Normalize canonical schema**
   - Define one authoritative `SongData` and `PlaylistData` schema.
   - Align all mappers/adapters/clients to those field names.
2. **Fix reference contract**
   - Standardize on `SourceRef.external_id` usage across all sources.
3. **Implement generic `Diff` model**
   - Implement `domain/diffs.py` and ensure adapter `compute_diff()` works.
4. **Clean plugin wiring**
   - Make `mm-pull` functional (no `quit()`), correct platform registry, proper exceptions.

## Phase 1 — Ingestion + identity graph
1. **Ingestion snapshots**
   - Persist pulled songs/playlists from each source into staging tables or a state store.
2. **Identity linking**
   - Build canonical song identity graph: map source IDs (`spotify_id`, `youtube_id`, beets item id, path, etc.) to one canonical song record.
3. **Deterministic matching policy**
   - Start with strict rules (exact source-id matches), then fallback to normalized text/fuzzy matching.

## Phase 2 — Matching/normalization/merge
1. **Normalization engine**
   - Implement title/artist normalization rules (feat/remix parsing, casing, punctuation).
2. **Matching engine** (`domain/matching.py`)
   - Multi-pass matching with confidence scores and explainability.
3. **Merge policy** (`domain/merging.py`)
   - Per-field precedence strategy (e.g., beets for local metadata, Spotify/YouTube for platform ids).
   - Conflict records for manual review when confidence low.

## Phase 3 — Sync execution engine
1. **Song sync planner**
   - Compute diffs per source from canonical desired state.
2. **Playlist sync planner**
   - Use field + membership diffs, support add/remove/move.
3. **Apply layer with dry-run**
   - `--dry-run`, `--apply`, and detailed operation logs.
4. **Idempotency and retries**
   - Track sync runs and avoid repeated churn.

## Phase 4 — Source expansion
1. **Rekordbox source**
   - Parse XML tracks/playlists, stable refs from TrackID + location.
2. **Filesystem source**
   - Scan paths, parse tags/filename, map to canonical.
3. **String source**
   - Use `SongStringParser` for free-form queue inputs.
4. **SoundCloud source**
   - Add client/adapter once auth + scope strategy is selected.

## Phase 5 — Soulseek integration
1. **Missing-file detector**
   - Derive “known in library but missing on disk” from canonical state.
2. **Download workflow**
   - Route unresolved missing songs into Soulseek search/downloader service.
3. **Post-download ingestion**
   - Re-import downloaded files, tag/update beets, and relink identities.

## 5) Suggested near-term deliverables (first milestone)

A realistic first milestone for fast progress:
1. Make `mm-pull --platform={spotify,youtube,beets,all}` fully work.
2. Implement and test `domain/diffs.py` + fix `SourceRef` usage.
3. Finalize `SongData` schema + update all mappers.
4. Add basic persistence of ingested songs/playlists to one canonical table set.
5. Add smoke tests for each source pull command and mapper conversions.

That gives you a usable “ingest + observe + compare” loop, after which matching/merging/sync can be implemented incrementally.
