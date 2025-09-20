-- Database init script for Finance Helper
-- This runs automatically on first Postgres container start
-- Place additional bootstrap SQL here (schemas, seeds, extensions)

-- Ensure we are on the expected database
-- Note: POSTGRES_DB is created automatically; this script runs within it

-- Optional extensions
-- Uncomment if needed and available in the image
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Example schema namespace (optional)
-- CREATE SCHEMA IF NOT EXISTS finance;

-- You can pre-create tables if not using Alembic yet
-- Keeping empty to let SQLAlchemy/Alembic handle migrations