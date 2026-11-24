-- Storefront image for products (populated when a supplier submission is approved).
ALTER TABLE products
  ADD COLUMN image_url VARCHAR(500) NULL AFTER warranty;
