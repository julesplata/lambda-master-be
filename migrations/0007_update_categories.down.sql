-- Remove added categories
DELETE FROM categories WHERE slug IN ('frontend', 'security', 'databases', 'devops');

-- Revert Backend to Architecture
UPDATE categories SET name = 'Architecture', slug = 'architecture' WHERE slug = 'backend';
