# muziekmachine — LLM Context & Architecture Guide

This document captures the **current shared understanding** of muziekmachine goals,
architecture, and design tradeoffs from recent implementation sessions.
It is intended to bootstrap future LLM sessions quickly.

---

## 1) Project Goal (product-level)

Muziekmachine is a multi-source music reconciliation/sync plugin for beets.

Primary outcomes:
- Pull songs and playlists from sources (Spotify, YouTube, beets now; more later).
- Normalize source payloads into canonical domain objects.
- Match/merge songs across sources into one canonical beets representation.
- Sync playlist metadata/membership across sources safely and deterministically.
- Keep the system powerful but understandable.

---

## 2) Architectural intent (layered)

### Source client (transport)
Responsible for API/session/auth/pagination and source-side operations.
Examples: list playlists, list playlist items, search candidates, create/delete/sync playlists.

### Source mapper (raw -> canonical)
Pure transformation of raw source payloads into domain models (`SongData`, `PlaylistData`).
No I/O orchestration logic.

### Source adapter (integration boundary)
Bridges client I/O with domain semantics:
- `to_songdata` (delegates mapper)
- identity refs (`make_ref`)
- source-native projections for diffing (`render_current`, `render_desired`)
- capability boundaries (`capabilities`, playlist capabilities)

### Services (workflow orchestration)
Composes clients/adapters/domain primitives into pull/ingest/sync flows.

### Domain (policy & canonical data)
Holds canonical models and deterministic logic:
- field diffs,
- membership diffs,
- matching,
- merging,
- playlist merge planning.

---

## 3) Canonical model decisions

### Song canonical object
`SongData` is the canonical cross-source representation for matching/merging and persistence.
All source song mappers should produce `SongData`.

### Source references
`SourceRef.external_id` is the preferred identity field.
`id` aliases may exist for backward compatibility, but new code should use `external_id`.

### Playlist canonical object
`PlaylistData` represents playlist metadata + ordered membership.

### Membership representation
`PlaylistData.members` stores `SongPointer` objects (identity pointers), not full `SongData` payloads.
This is intentional for deterministic diff/sync behavior.

---

## 4) Why pointer-based playlist membership (core design tradeoff)

Pointer-first membership is preferred for sync planning because it gives:
- deterministic equality (`spotify:<id>`, `youtube:<id>`, `song:<canonical_id>`),
- idempotent add/remove/move plans,
- direct mapping to source API mutation operations,
- lower risk of false positives vs fuzzy metadata equality.

`SongData` is still used heavily for matching/merge and analysis.

---

## 5) “Hydration layer” clarification

Hydration is **optional** and should be lightweight.

- If beets is the canonical read model for UI/analysis, a large separate hydration subsystem is unnecessary.
- A small resolver utility can still be useful inside pipeline execution to map pointers/raw items to canonical `SongData` before persistence finalization.

Practical stance:
- Keep pointer-based membership for diff/sync.
- Use beets canonical data for long-term UX/query surfaces.
- Add hydration helpers only where execution flow needs them.

---

## 6) Pipeline modes we care about

- Pull one playlist from one source.
- Pull all playlists from one source.
- Pull from all sources.
- Sync one playlist across sources.
- Merge incoming songs into canonical beets entities.

All modes should converge to the same canonical contracts (SongData + PlaylistData + pointers).

---

## 7) Current conventions to keep

- Playlist selector behavior supports exact id, exact name, and partial-name matching.
- Source clients advertise unsupported operations via capability errors.
- Spotify implementation targets Spotipy versions compatible with Spotify Feb-2026 API shape.
- Playlist mappers should not return placeholder `None` for required conversions.

---

## 8) Known practical constraints / risks

- Some source APIs evolve quickly (Spotify especially): endpoint semantics can change by app tier.
- Source “delete playlist” semantics may differ (unfollow vs delete vs library remove).
- Mapping heuristics (artist/title/remix parsing) remain imperfect and should be treated as evolving rules.

---

## 9) Implementation heuristics for future sessions

When adding/changing features, prefer this order:
1. Tighten domain contract (model fields + invariants).
2. Ensure mapper completeness (raw -> canonical always returns valid objects).
3. Update adapter projections/capabilities.
4. Update source client calls.
5. Add focused tests for the changed contract.

---

## 10) Minimum checklist before claiming “pipeline-ready”

- [ ] SourceRef usage is consistent (`external_id` first).
- [ ] All required mapper methods implemented (no TODO/`return` stubs on active paths).
- [ ] Playlist member key rendering is consistent across sources.
- [ ] Ingestion selectors are consistent across services.
- [ ] Source capability behavior is explicit and tested.
- [ ] At least one contract test exists for changed source methods.

---

## 11) Scope boundary (important)

This plugin is not trying to build a second long-term canonical DB outside beets.
Beets is intended to be the canonical persisted view for merged songs and playlist-song relations.

Domain/service objects are orchestration and transformation contracts around that canonical store.
