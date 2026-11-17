-- Name common products in ten existing question stems.
--
-- Ten generic question stems now name a common product as an example (Nginx,
-- RabbitMQ, Amazon SQS, Elasticsearch, AWS Lambda, PostgreSQL, ...), alongside
-- the named-product seed files added in the same change. Bulk import rejects
-- titles that already exist, so a database seeded before the edit only gets the
-- new stems through this migration.
--
-- Each row is matched on (category slug, question title, old description). A
-- stem already edited through the admin console no longer matches and is left
-- alone, and rerunning the migration is a no-op. Only the description changes:
-- options, answers and ids are untouched, so past attempts stay valid.

BEGIN;

UPDATE questions
SET description = changes.new_description, updated_at = NOW()
FROM (VALUES
    ('system-design', 'Purpose of a load balancer', 'What is the primary purpose of placing a load balancer in front of a pool of identical application servers?', 'What is the primary purpose of placing a load balancer, such as Nginx or an AWS Application Load Balancer, in front of a pool of identical application servers?'),
    ('system-design', 'Reverse proxy role', 'Which function is commonly handled by a reverse proxy?', 'Which function is commonly handled by a reverse proxy such as Nginx or HAProxy?'),
    ('system-design', 'Message queue purpose', 'What is the primary benefit of putting a message queue between a producer and a consumer service?', 'What is the primary benefit of putting a message queue, such as RabbitMQ or Amazon SQS, between a producer and a consumer service?'),
    ('system-design', 'Time-series database fit', 'Which workload is a time-series database optimized for?', 'Which workload is a time-series database, such as InfluxDB or TimescaleDB, optimized for?'),
    ('system-design', 'API gateway responsibilities', 'Which responsibility is commonly centralized in an API gateway?', 'Which responsibility is commonly centralized in an API gateway, such as Kong or Amazon API Gateway?'),
    ('system-design', 'Service discovery', 'What problem does service discovery solve in a microservices architecture?', 'What problem does service discovery, as provided by tools like Consul or Kubernetes Services, solve in a microservices architecture?'),
    ('system-design', 'Inverted index for search', 'What is the core data structure behind a full-text search engine, and what does it map?', 'What is the core data structure behind a full-text search engine such as Elasticsearch, and what does it map?'),
    ('system-design', 'Cold start in serverless', 'What causes a ''cold start'' latency spike in serverless functions?', 'What causes a ''cold start'' latency spike in serverless functions such as AWS Lambda?'),
    ('system-design', 'Dead letter queue purpose', 'What is a dead letter queue (DLQ) used for?', 'What is a dead letter queue (DLQ), such as one attached to an Amazon SQS queue, used for?'),
    ('database', 'What VACUUM/compaction addresses', 'In MVCC databases, what problem does a process like VACUUM (or compaction) address?', 'In MVCC databases such as PostgreSQL, what problem does a process like VACUUM (or compaction) address?')
) AS changes (category_slug, question_title, old_description, new_description)
JOIN categories ON categories.slug = changes.category_slug
WHERE questions.category_id = categories.id
    AND questions.title = changes.question_title
    AND questions.description = changes.old_description;

COMMIT;
