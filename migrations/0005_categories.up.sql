-- Create categories table with a closed, seeded vocabulary
CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name varchar(50) UNIQUE NOT NULL,
    slug varchar(50) UNIQUE NOT NULL,
    position int NOT NULL DEFAULT 0
);

INSERT INTO categories (name, slug, position) VALUES
    ('Architecture',    'architecture',    1),
    ('OOP',             'oop',             2),
    ('Design Patterns', 'design-patterns', 3),
    ('Coding',          'coding',          4);

-- Add category_id to questions; allow NULL initially so existing rows don't break
ALTER TABLE questions ADD COLUMN category_id uuid REFERENCES categories(id) ON DELETE RESTRICT;

-- Backfill existing rows to 'coding' (change to whatever makes sense for your data)
UPDATE questions SET category_id = (SELECT id FROM categories WHERE slug = 'coding');

-- Now enforce NOT NULL
ALTER TABLE questions ALTER COLUMN category_id SET NOT NULL;
