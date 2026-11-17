-- Link the quizzes one browser takes.
--
-- The frontend keeps a random UUID in localStorage once a visitor accepts
-- analytics, and sends it as X-Visitor-Id. POST /quiz-attempts stores it here,
-- so completed attempts can be grouped per visitor (return visits, and leaving
-- out the owner's own browser). NULL for visitors who have not accepted, who
-- declined, or who send Global Privacy Control, and for every earlier row.
--
-- The partial index serves per-visitor lookups by time and skips the NULL rows,
-- which are most of the table. ADD COLUMN with no default does not rewrite it.

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN visitor_id UUID;

CREATE INDEX idx_quiz_attempts_visitor_started
    ON quiz_attempts (visitor_id, started_at)
    WHERE visitor_id IS NOT NULL;

COMMIT;
