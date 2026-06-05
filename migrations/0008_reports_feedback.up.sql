-- Question reports: users flag something wrong with a specific question.
CREATE TABLE question_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id uuid NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    -- Optional context of which quiz the report came from. No FK, mirroring the
    -- guest-attempt pattern: it stays valid even if the attempt is gone.
    attempt_id uuid,
    reason varchar(20) NOT NULL,
    comment text,
    status varchar(10) NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT question_reports_reason_check
        CHECK (reason IN ('incorrect_answer', 'typo', 'unclear', 'outdated', 'other')),
    CONSTRAINT question_reports_status_check
        CHECK (status IN ('open', 'resolved', 'dismissed'))
);

CREATE INDEX idx_question_reports_question_id ON question_reports (question_id);
CREATE INDEX idx_question_reports_status ON question_reports (status);

-- App feedback: free-form, app-wide feedback not tied to any question.
CREATE TABLE app_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category varchar(20) NOT NULL,
    message text NOT NULL,
    rating smallint,
    status varchar(10) NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_feedback_category_check
        CHECK (category IN ('bug', 'idea', 'praise', 'other')),
    CONSTRAINT app_feedback_rating_check
        CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    CONSTRAINT app_feedback_status_check
        CHECK (status IN ('open', 'reviewed'))
);

CREATE INDEX idx_app_feedback_status ON app_feedback (status);
