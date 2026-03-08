# muziekmachine pipeline refinement (pre-implementation)

This document captures the agreed high-level pipeline direction before coding runtime behavior:

1. Pull data from sources.
2. Diff/match data across sources.
3. Sync and persist the resolved result into beets.

It is intentionally **planning-only**.

---

## 1) Current-state grounding

Based on `LLM_CONTEXT.md`, `STATUS_REVIEW.md`, and current code:

- Canonical contracts exist for songs/playlists (`SongData`, `PlaylistData`, `SongPointer`).
- Generic ingestion helpers exist (`pull_source`, `iter_playlist_data`) and playlist diff logic already exists.
- Top-level orchestration is still incomplete for robust multi-source execution.

---

## 2) Pipeline boundaries (locked)

### Pull phase
- Purpose: fetch playlists + song memberships from source platforms.
- Output: **in-memory objects only**.
- Non-goal: no writes to beets and no staging DB/table/file.

### Diff/matching phase
- Purpose: compare source snapshots, resolve identities, and build a unified desired state.
- Output: in-memory sync plan / desired membership state.
- Non-goal: no source mutation yet.

### Sync phase
- Purpose: apply decided changes.
- This phase is responsible for:
  - mutating source playlists when needed,
  - persisting the final resolved/canonical state into beets.

---

## 3) Refined command surface (near-term)

### `mm-pull-playlists`
Initial shape:
- `--platform {spotify,youtube,beets,all}` (`all` includes beets)
- `--playlist <selector1,selector2,...>` (optional explicit selectors)
- if no explicit selector: use config default naming pattern(s)
- `--limit <n>` for fast validation runs
- log-focused output

### `mm-pull-songs`
Initial shape:
- same platform/selector defaults
- for collection-bound sources (spotify/youtube), songs are pulled in playlist context
- include playlist context fields (`playlist_id`, `playlist_name`, `position` where available)

### Future
- diff/matching command (name TBD)
- sync command (name TBD) that performs final persistence to beets

---

## 4) Core behavior decisions from refinement

1. **Default scope**
   - Pull config-matching playlists by default.
   - Explicit selectors override defaults.

2. **Failure handling**
   - Source failures are isolated: continue other sources and report failures clearly.

3. **Ordering**
   - Preserve playlist membership order during pull.

4. **Deduping**
   - Pull does not perform destructive dedupe.
   - Deduping/matching decisions belong to diff/matching phase.

5. **Storage policy (for now)**
   - No staging storage for pull output.
   - Keep pull/diff/sync handoff in memory inside one pipeline run.

6. **Beets write policy (for now)**
   - Pull phase does not update beets.
   - Beets persistence happens after sync decisions are made.

7. **Retry policy**
   - Retries with backoff for transient source failures.

---

## 5) Membership semantics

To support multi-source workflows safely:

### Default mode: additive interpretation during pull/diff
- Source absence does not immediately imply canonical removal.
- Membership removals are decided only in sync policy.

### Optional authoritative mode (later)
- A selected source/source-set can be treated as authoritative for a run.
- In that mode, non-present members may be removed during sync.
- This should remain explicit opt-in via sync-level flags.

---

## 6) Proposed implementation phases

### Phase 1 — Pull functionality (spotify + youtube focus)
Deliverables:
- implement `mm-pull-playlists` and `mm-pull-songs`
- config-default selector behavior + explicit selector overrides
- in-memory result objects with per-source counters/errors in logs
- no beets writes

### Phase 2 — Diff/matching layer
Deliverables:
- identity resolution across pulled source data
- unified desired playlist membership model
- explicit removal policy inputs for later sync

### Phase 3 — Sync + beets persistence
Deliverables:
- apply mutations to selected source targets
- persist final resolved state into beets
- support conservative default mode plus optional authoritative mode

### Phase 4 — Hardening
Deliverables:
- improved operational diagnostics
- expand test coverage after initial functional validation runs

---

## 7) Immediate next coding slice recommendation

1. Add pull commands (`mm-pull-playlists`, `mm-pull-songs`) with spotify/youtube support.
2. Wire config-default playlist filtering + explicit selectors.
3. Implement resilient multi-source execution (continue on failure, retry with backoff).
4. Produce clear logs and in-memory pull outputs for next-stage diff/matching.
5. Defer all beets writes to the sync phase.

---

## 8) Concrete build plan for Phase 1 (start coding checklist)

### Step 1 — Command scaffolding and routing
Files:
- `beetsplug/muziekmachine/__init__.py`

Tasks:
- add `mm-pull-playlists` and `mm-pull-songs` subcommands.
- add shared options: `--platform`, `--playlist`, `--limit`.
- ensure platform choices are at least `spotify`, `youtube`, `beets`, `all`.
- route into one shared pull orchestration path (avoid duplicating control flow).

Done when:
- both commands show in `beet help` and dispatch correctly by platform.

### Step 2 — Selector resolution contract
Files:
- `beetsplug/muziekmachine/services/playlist_ingestion.py`
- `beetsplug/muziekmachine/services/ingestion.py`

Tasks:
- keep existing explicit selector semantics (`id`, exact name, partial name).
- if `--playlist` is omitted, resolve selector patterns from config defaults.
- centralize this logic once so spotify and youtube behave identically.

Done when:
- a no-selector run only pulls config-matching playlists.
- explicit selector run overrides defaults.

### Step 3 — In-memory pull result model
Files:
- `beetsplug/muziekmachine/domain/models.py` (or a dedicated pull-result module)
- `beetsplug/muziekmachine/services/ingestion.py`

Tasks:
- define a lightweight pull run result object containing:
  - source name,
  - playlists scanned,
  - songs seen,
  - duplicates observed,
  - mapping failures,
  - fatal/non-fatal errors.
- ensure command handlers only log + return in-memory results.
- explicitly avoid any beets write path in pull commands.

Done when:
- pull command returns/logs structured per-source summaries with no DB mutation calls.

### Step 4 — Retry/backoff and failure isolation
Files:
- `beetsplug/muziekmachine/sources/*/client.py`
- `beetsplug/muziekmachine/services/ingestion.py`

Tasks:
- wrap transient source calls with bounded retry + backoff.
- classify errors into retryable vs non-retryable.
- continue other sources when one source fails; record the failure in summary logs.

Done when:
- one broken source does not abort pulling from remaining sources.

### Step 5 — Song pull behavior for playlist-context sources
Files:
- `beetsplug/muziekmachine/sources/spotify/mapper.py`
- `beetsplug/muziekmachine/sources/youtube/mapper.py`
- `beetsplug/muziekmachine/services/playlist_ingestion.py`

Tasks:
- confirm mapping includes playlist context (`playlist_id`, `playlist_name`, `position` where available).
- keep order-preserving membership in memory.
- do not dedupe destructively in pull stage.

Done when:
- logs can show playlist-level song counts and preserved order.

### Step 6 — Minimal runtime validation protocol (before tests)
Commands to run manually after implementation:
- `beet mm-pull-playlists --platform spotify --limit 1`
- `beet mm-pull-playlists --platform youtube --limit 1`
- `beet mm-pull-songs --platform all --limit 1`

Validation checklist:
- command completes without beets writes,
- per-source summary logs are present,
- failures are isolated,
- selector defaulting works,
- playlist context fields are visible in debug logs.

### Step 7 — Code freeze criteria for Phase 1
Phase 1 is complete when:
- pull commands are stable for spotify + youtube,
- output is in-memory + logged summaries only,
- no direct beets persistence exists in pull flow,
- known failures are captured in logs with enough detail to start Phase 2 diff/matching implementation.
