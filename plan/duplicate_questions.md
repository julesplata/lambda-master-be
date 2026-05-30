mitigate duplicate question plan

Layer 1 — Exact-dedupe with a content hash (do this first)
The most robust defense is a database-enforced uniqueness constraint, because it can't be bypassed by a buggy endpoint, a re-run seed, or a race between two concurrent requests. The DB is the single chokepoint.

Add a content_hash column: a normalized hash of the question's defining content.

Exact dedupe (do first). Add a content_hash column to questions = SHA-256 of normalize(title) + normalize(description), where normalize lowercases and collapses whitespace. Enforce with a UNIQUE index (DB-level, so nothing can bypass it). Make the bulk endpoint use ON CONFLICT (content_hash) DO NOTHING → seeds become idempotent and re-runs insert nothing.

Note on your choice: hashing title+description (not options) means two questions with identical wording but different answer choices will collide and the second is treated as a dup. That's usually what you want; just flagging it so it's not a surprise.


# app/core/dedup.py
import hashlib

def normalize(text: str) -> str:
    # lowercase + collapse whitespace so trivial formatting differences collide
    return " ".join(text.lower().split())

def question_fingerprint(title: str, description: str, options: list[str]) -> str:
    parts = [normalize(title), normalize(description)]
    # sort options so reordering them doesn't dodge the hash
    parts += sorted(normalize(o) for o in options)
    joined = "\x1f".join(parts)  # unit separator avoids accidental collisions
    return hashlib.sha256(joined.encode()).hexdigest()
Then a migration adds the column + unique index:


ALTER TABLE questions ADD COLUMN content_hash CHAR(64);
-- backfill existing rows here, then:
ALTER TABLE questions ALTER COLUMN content_hash SET NOT NULL;
CREATE UNIQUE INDEX questions_content_hash_uq ON questions (content_hash);
Key decision: what counts as "the same question?" That's the only judgment call here — do you want a duplicate to be (a) title only, (b) title + description, or (c) title + description + option set? I'd recommend (b) or (c). Hashing options too means two questions with identical wording but different answer choices are allowed to coexist; hashing title-only is aggressive and may reject legitimate variations.

In the bulk endpoint you then either skip-or-error on conflict using Postgres ON CONFLICT:


# skip duplicates silently, report counts
stmt = insert(Question).values(...).on_conflict_do_nothing(
    index_elements=["content_hash"]
).returning(Question.id)
This makes your seed idempotent — re-running it inserts nothing the second time, which also fixes the "re-run the seed" footgun.

Layer 2 — Near-duplicate detection (semantic)

Near-dupe flagging (when manual entry starts). Enable pg_trgm, GIN index on title, and at insert/review time surface the top similar existing questions (similarity > ~0.6) as an advisory warning, not a hard block. Upgrade to embeddings + pgvector nearest-neighbor only once paraphrase duplicates become a real problem at scale.

A hash won't catch reworded duplicates. Two complementary approaches:

Trigram / fuzzy similarity (cheap, in-Postgres). Enable pg_trgm and check similarity of incoming title+description against existing rows. Flag anything above a threshold (e.g. similarity > 0.6) for human review rather than auto-rejecting:


CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX questions_title_trgm ON questions USING gin (title gin_trgm_ops);
-- at insert/review time:
SELECT id, title, similarity(title, :incoming) AS s
FROM questions WHERE title % :incoming ORDER BY s DESC LIMIT 5;
Good for catching typo-level and minor-rewording dupes. Weak on true paraphrases.

Embeddings + vector similarity (strong, more infra). Embed each question once, store the vector (e.g. pgvector), and on insert do a nearest-neighbor search; cosine similarity above a threshold means "probable duplicate → flag for review." This catches "Purpose of a load balancer" vs "What does a load balancer do?" that trigrams miss. Given you're already in an AI-adjacent project, this is the most effective option as the bank scales, but it's the heaviest.

Layer 3 — Process / workflow

Make near-dupe detection advisory, not blocking — surface "3 similar questions already exist" in the admin UI and let a human decide. Auto-rejecting paraphrases will eventually block legitimate questions.
Add a periodic batch job that scans the whole bank for similar pairs and queues them for review, catching dupes that slipped in before the checks existed.