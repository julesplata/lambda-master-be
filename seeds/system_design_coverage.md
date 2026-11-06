# Seed Questions — Expansion Guide

Working reference for adding seed questions without creating duplicates.

**Current inventory:** generated, not hand-maintained. Run:

```bash
python seeds/generate_coverage.py
```

This validates every seed file against the API schema, rejects duplicate
`(title, category)` and `(concept, format, category)` pairs, and rewrites
[`coverage_report.md`](coverage_report.md) — the source of truth for what
questions exist, grouped by category with per-concept format and difficulty.
Never edit `coverage_report.md` by hand, and never hand-maintain counts or
concept lists in this file.

Every question carries two extra fields beyond the API schema (the bulk
endpoint ignores them):

- `concept` — kebab-case slug of the concept tested (for recall questions this
  is the slugified title). Two questions with the same `(concept, format,
  category)` are duplicates and the generator rejects them.
- `format` — `recall` (definition/trade-off stem) or `situational`
  (scenario stem ending in an applied question).

## How to use this document

When adding new questions:

1. **Regenerate and check [`coverage_report.md`](coverage_report.md)** before writing a question. If the concept already appears in your target format, either skip it or make sure your new question tests a *distinct angle* under a new concept slug (e.g. existing "LRU eviction" vs. a new "LFU eviction" is fine; a second "what does LRU evict" is a dup).
2. **Pull from the Gap List** at the bottom — those are concepts with little or no coverage, so they're the safest expansion targets. Strike gaps off the list as you cover them.
3. **Match the existing schema** (see template at the end) including `concept` and `format`.
4. **Keep option lengths comparable.** Write distractors as carefully as the answer: the generator fails if the correct option is more than 1.3x the median distractor length, or if one length rank (longest, second longest, ...) holds more than 40% of a file's correct answers. Vary which option is longest.
5. **Rerun `python seeds/generate_coverage.py`** — it fails loudly on schema errors and duplicates, and refreshes the report.

### Dedup rule of thumb
A question is a duplicate if a learner who can answer an existing question can answer the new one without learning anything new. Same concept + different scenario wording = still a dup. Different concept (even adjacent) = keep.

### Situational set (deliberate exception to the dedup rule)
[`system_design_situational_questions.json`](system_design_situational_questions.json) (50 questions, added 2026-07-10) is a different **format**, not new concepts: each question is a 2–4 sentence real-world scenario ending in an applied question ("What is the best first improvement?", "What is the most likely cause?"), testing application rather than recall. These intentionally revisit concepts already covered in recall form, so the dedup rule applies *within* each format, not across formats — a recall question and a situational question on the same concept may coexist, but two situational questions on the same concept are still a dup.

## Named products: verify before writing

[`system_design_products_questions.json`](system_design_products_questions.json)
(31 questions) and [`database_products_questions.json`](database_products_questions.json)
(13 questions), added 2026-11-06, test common named products: Redis, Kafka,
RabbitMQ, Amazon SQS, S3, CloudFront, AWS Lambda, API Gateway, Nginx, Docker,
Kubernetes, Prometheus, OpenTelemetry, PostgreSQL, PgBouncer, MySQL InnoDB,
MongoDB, DynamoDB, SQLite, Cassandra and Elasticsearch. Ten older generic stems
also gained a product example (migration `0011`).

Product facts drift. Check each one against the vendor's docs when you write
it, not from memory, and re-check the questions below when a source ships a
breaking change, and at least every six months.

| Source checked on 2026-11-06 | Questions that depend on it |
|---|---|
| Redis docs (eviction, persistence, cluster spec, KEYS) | Redis cache starts rejecting writes; Redis RDB vs AOF persistence; Multi-key command fails in Redis Cluster; One command freezes the Redis cache |
| Memcached docs | Redis vs Memcached |
| Apache Kafka docs (broker and producer configs, design) | Acknowledged Kafka writes lost; Extra Kafka consumers sit idle; Kafka retention vs a classic queue |
| Amazon SQS developer guide | SQS jobs run twice; SQS standard vs FIFO queues |
| RabbitMQ AMQP concepts and topics tutorial | RabbitMQ exchange types |
| Amazon S3, CloudFront, Lambda, RDS Proxy, API Gateway and ELB docs | Amazon S3 read-after-write consistency; CDN hit rate stuck near zero; AWS Lambda maximum run time; Lambda spike exhausts Postgres connections; API keys in Amazon API Gateway; Layer 4 vs layer 7 load balancing |
| nginx proxy module docs | Nginx returns 504 errors |
| Kubernetes docs (probes, resource management, HPA, Deployments) | Kubernetes liveness vs readiness probes; Liveness probe restarts every pod; Kubernetes CPU vs memory limits; Autoscaler never adds pods; Updating a Kubernetes Deployment |
| Docker build cache and image docs | Docker image vs container; Every Docker build reinstalls dependencies |
| Prometheus and OpenTelemetry docs | How Prometheus collects metrics; Prometheus runs out of memory; What OpenTelemetry provides |
| PostgreSQL docs (CREATE INDEX, EXPLAIN, JSON types, isolation) and PgBouncer docs | Adding an index blocks checkout; EXPLAIN ANALYZE on a DELETE; Slow queries on a JSONB column; PgBouncer transaction pooling |
| MySQL 8.4 InnoDB docs | InnoDB secondary index lookups |
| MongoDB manual (limits, write concern, rollbacks) | Popular post stops accepting comments; MongoDB write concern majority; MongoDB embedding vs referencing; How MongoDB stores data |
| DynamoDB developer guide | DynamoDB partition key and sort key; DynamoDB lookup gets slower every month; Order missing from a DynamoDB index query |
| SQLite WAL and "when to use" pages | SQLite with many concurrent writers |
| Elasticsearch near real-time search docs | New product missing from search results |

Not re-fetched, because it is long-standing documented behavior: Cassandra
LOCAL_QUORUM.

### Facts most likely to drift

- **AWS Lambda's 15-minute limit** applies to standard functions. Lambda
  Managed Instances allow longer async runs, so the question says "standard".
- **MongoDB's default write concern** is majority since 5.0, with an exception
  for some arbiter setups. Majority writes resist rollback only with journaling,
  which is on by default.
- **PgBouncer prepared statements** now work in transaction pooling
  (max_prepared_statements), so the PgBouncer question uses SET, not PREPARE.
- **Elasticsearch's refresh interval** is 1s on searched indices in the Elastic
  Stack and 5s on Serverless. The question's explanation says "every second",
  which is the Elastic Stack default.
- **The MongoDB document limit** is 16 MiB; write it that way.

---

## Gap List — safe expansion targets

These concepts have little or no coverage. Pull from here first.

> History: two 2026-06-05 expansions consumed the earlier gap lists. Caution —
> the "questions 101–150" batch (CRDTs, OAuth flows, CORS, OLTP/OLAP, merkle
> trees, etc.) does not appear in any seed file in this repo, so those concepts
> are absent from `coverage_report.md`; if a concept matters, treat it as an
> open gap unless the report shows it. The gaps below are targets not covered
> in any seed file.

### Real-time & messaging
- Protobuf/Thrift backward & forward compatibility (field number rules)
- Push vs pull notification delivery (mobile fan-out)
- Priority queues / message ordering guarantees beyond per-partition

### Storage & data
- Time-to-live / TTL-based row expiry in databases
- Append-only vs update-in-place storage trade-offs
- Columnar storage internals (run-length / dictionary encoding)
- Tombstones and their read-path / compaction cost

### Coordination & consensus
- Quorum intersection math (why majorities overlap)
- ZooKeeper / etcd as a coordination primitive (watches, ephemeral nodes)
- Lamport timestamps vs vector clocks

### Networking & delivery
- Backpressure propagation across a multi-stage pipeline
- TCP slow start / congestion control impact on tail latency
- Connection pooling exhaustion under load

### Operations & cost
- Cost-aware architecture trade-offs (egress, storage tiers)
- Multi-tenancy isolation (noisy-neighbor mitigation)
- Blast-radius reduction (cell-based architecture)

---

## Question template

Match this exact shape (one correct option, three plausible distractors). Order of options can vary; the app randomizes display.

```json
{
  "title": "Short concept name",
  "description": "The question stem ending in a question mark?",
  "difficulty": "beginner | intermediate | advanced",
  "explanation": "1–2 sentences on why the correct answer is right.",
  "options": [
    { "text": "Correct answer", "is_correct": true },
    { "text": "Plausible distractor", "is_correct": false },
    { "text": "Plausible distractor", "is_correct": false },
    { "text": "Plausible distractor", "is_correct": false }
  ],
  "category": "system-design",
  "concept": "kebab-case-concept-slug",
  "format": "recall | situational"
}
```

### Authoring conventions (observed in existing set)
- **Difficulty = target seniority.** Calibrate to the engineer who should answer
  it correctly, not to how obscure the topic sounds:
  - `beginner` — **junior engineer.** Definitions and recognition: what a
    component is, what it's for, which term names a given idea.
  - `intermediate` — **mid-level engineer.** Trade-offs and mechanics: why you'd
    pick one option over another, how a thing behaves under normal load.
  - `advanced` — **senior engineer.** Failure modes, internals, and
    distributed-systems subtleties: what breaks under partial failure and why.
- **Distractors** should be wrong but believable — common misconceptions or adjacent concepts, not absurd options.
- **Explanation** states the rule, not just "correct answer is A."
- Keep `title` to a short noun phrase; keep `description` to a single question.
- **Situational set:** `title` is a short scenario name ("Checkout waits on the email server"); `description` is the 2–4 sentence scenario ending in the applied question.

### Loading new questions
Per [CLAUDE.md](../CLAUDE.md), load via `POST /api/v1/questions/bulk` with the `X-Admin-Key` header. The endpoint accepts the same `{ "questions": [...] }` envelope as this seed file.
