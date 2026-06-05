-- Rename Architecture to Backend
UPDATE categories SET name = 'Backend', slug = 'backend' WHERE slug = 'architecture';

-- Add new categories
INSERT INTO categories (name, slug, position) VALUES
    ('Frontend',  'frontend',  5),
    ('Security',  'security',  6),
    ('Databases', 'databases', 7),
    ('DevOps',    'devops',    8);
