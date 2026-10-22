# Architecture — Customer Data Platform

## Component view

```
  web / mobile / CRM / POS / support
              │
              ▼
       ┌─────────────┐   validation · normalisation
       │  Ingestion   │   event-id deduplication
       └──────┬──────┘
              │ events + profile fragments
              ▼
       ┌──────────────────┐   deterministic: shared user_id/email/phone
       │ Identity          │   probabilistic: name/city/device/anon score
       │ resolution        │   >=0.85 auto-link · 0.60–0.85 review
       └──────┬───────────┘
              │                     audit log: merge · split · link · erase
              ▼
       ┌──────────────────┐
       │ Unified profile   │   identifiers accumulate
       │ store             │   descriptive fields latest-wins
       └───┬──────────┬───┘
           │          │
           ▼          ▼
   ┌────────────┐  ┌────────────┐      ┌──────────────┐
   │ Consent     │  │ Segments    │─────▶│ Activation    │
   │ per purpose │  │ field/trait │      │ webhook/file  │
   │ + erasure   │  │ /event rules│      │ consent-gated │
   └────────────┘  └────────────┘      └──────────────┘
           │
           ▼
   ┌────────────┐
   │ Data quality│  coverage · duplicates · erasure leaks
   └────────────┘
              │
              ▼
   FastAPI / CLI: /profiles /events /fragments /consent
                  /segments /activate /quality /audit
```

## Data flow, step by step

1. **Ingest.** Events and profile fragments arrive from any source.
   Emails are lower-cased, phones reduced to digits (US country code
   stripped). Records with no identifier, a bad timestamp or a
   malformed email are rejected with specific reasons. Event ids are
   deduplicated, so redelivery is safe.
2. **Resolve identity.** Each fragment is matched against active
   profiles. A shared strong identifier (user_id, email, phone) is a
   deterministic link at score 1.0. Otherwise a probabilistic score
   blends name similarity, city, shared device and shared anonymous
   id. At or above the auto-link threshold (0.85) the fragment joins
   that profile; between the review threshold (0.60) and 0.85 the
   match is audit-logged and a new profile is created instead.
3. **Unify.** Identifiers accumulate on the profile; descriptive
   fields (name, city, country, traits) are latest-wins by the
   fragment's `observed_at`, so a stale CRM export cannot overwrite a
   fresher app profile. Events increment counts and record types.
4. **Enforce consent.** Consent lives per profile per purpose
   (marketing, analytics, personalisation, support, transactional).
   UNKNOWN denies everything except transactional; DENIED denies
   everything. Enforcement happens where data is *used* — segment
   activation — not just where consent is stored.
5. **Build segments.** Rules address profile fields, `trait.<key>`
   values, or event history, combined with AND/OR. A segment declares
   the purpose it will be activated for.
6. **Activate.** The activator filters segment members through
   consent for that purpose, builds minimal payloads (identifiers +
   traits), and delivers to a sink (webhook recorder or JSON-lines
   file in this build). Delivered and skipped-no-consent counts are
   both reported.
7. **Erase.** A deletion request wipes every identifier, name and
   trait from the profile, marks it erased, and writes an audit
   entry. The tombstone remains so downstream systems and the
   erasure-leak quality check can verify the wipe.
8. **Check quality.** Coverage, duplicate-email, orphan-event,
   erasure-leak and identifier-completeness checks run over the
   store as pure functions — in CI, in the demo, or on a schedule.

## Key decisions

### Why deterministic-first matching?

Strong identifiers are unambiguous evidence; a scoring model should
never outvote a shared verified email. Deterministic rules run first
and short-circuit, which also makes the common case cheap and the
audit reason human-readable ("shared email=…").

### Why does a review-band match create a *new* profile?

The alternative — holding fragments in a pending queue — couples
ingestion to a human workflow. Creating the profile keeps the
pipeline flowing, and the audit entry preserves the candidate link so
a later deterministic signal (or a steward's merge) can stitch them.
The cost is temporary duplicates, measured by the duplicate-email
quality check once identifiers arrive.

### Why latest-wins by `observed_at`, not arrival order?

Sources batch and redeliver out of order. Arrival order would let a
week-old CRM export overwrite yesterday's in-app update.
`observed_at` is the source's own clock for when the fact was true.

### Why is the activation payload minimal?

A CDP that ships full profiles to every destination multiplies PII
exposure. Payloads carry identifiers and traits only — enough to
target, not enough to reconstruct a record — and only for profiles
whose consent covers the segment's purpose.

### Why in-memory stores?

The build's value is the resolution, consent and activation logic,
none of which needs a database. Stores are small classes behind
plain interfaces; swapping in Postgres/Redis changes persistence,
not semantics, and keeps tests and the demo fully offline.

## Failure modes and what the platform does

| Failure | Behaviour |
|---|---|
| Event with no identifier | Rejected at ingestion with a named reason |
| Duplicate event delivery | Counted as duplicate; profile counts unchanged |
| Malformed email / bad timestamp | Rejected (batch) or raised (strict mode) |
| Probabilistic match in review band | New profile + audit entry; never auto-merged |
| Merge of a profile into itself / inactive profile | `MergeError` |
| Split of a never-merged profile | `SplitError` |
| Activation without consent | Profile skipped and counted, never delivered |
| Unknown segment / profile | Specific typed error naming the id |
| Erased profile still holding PII | `no_erased_data` quality check fails |

## Scaling notes (what production adds)

- **Streaming ingestion** (Kafka / Kinesis) in front of the ingestor,
  with the same validation and dedup contract.
- **A persistent identity graph** (profile ↔ identifier edges) so
  transitive stitching and steward merge/split UIs operate on the
  graph directly.
- **Consent receipts and jurisdiction policy packs**: the purpose
  model stays, the defaults vary by region.
- **Real activation sinks** — warehouse reverse-ETL, email/ad
  platforms — behind the two-method sink interface, with delivery
  receipts reconciled against the activation result.
- **DSAR export**: a per-profile bundle assembled from the store,
  consent records and audit log.
