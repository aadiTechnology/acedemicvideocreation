-- DRAFT, NOT RUN. Review, then run once as the server's admin role against the Identity PostgreSQL (psql -d postgres).
-- Replace every <...> placeholder with a password generated into Coolify secrets. Never commit real values.
-- Prerequisite: docker network create aadi-data (on the Coolify host) and the Identity stack redeployed with the shared network.

-- 1. Keep the identity database closed to everyone except its own role.
REVOKE CONNECT ON DATABASE identity FROM PUBLIC;

-- 2. Roles: a migrator (DDL) and a runtime role (no DDL) per product database.
CREATE ROLE aadi_academic_migrator LOGIN PASSWORD '<academic-migrator-password>' NOINHERIT;
CREATE ROLE aadi_academic_app      LOGIN PASSWORD '<academic-app-password>'      NOINHERIT;
CREATE ROLE aadi_video_engine_migrator LOGIN PASSWORD '<engine-migrator-password>' NOINHERIT;
CREATE ROLE aadi_video_engine_app      LOGIN PASSWORD '<engine-app-password>'      NOINHERIT;

-- 3. Databases, owned by the migrator roles.
CREATE DATABASE aadi_academic     OWNER aadi_academic_migrator;
CREATE DATABASE aadi_video_engine OWNER aadi_video_engine_migrator;
REVOKE CONNECT ON DATABASE aadi_academic     FROM PUBLIC;
REVOKE CONNECT ON DATABASE aadi_video_engine FROM PUBLIC;
GRANT CONNECT ON DATABASE aadi_academic     TO aadi_academic_migrator, aadi_academic_app;
GRANT CONNECT ON DATABASE aadi_video_engine TO aadi_video_engine_migrator, aadi_video_engine_app;

-- 4. In each database (\c aadi_academic, then \c aadi_video_engine): runtime role may change rows, not create tables.
--    \c aadi_academic
--    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
--    GRANT USAGE ON SCHEMA public TO aadi_academic_app;
--    ALTER DEFAULT PRIVILEGES FOR ROLE aadi_academic_migrator IN SCHEMA public
--      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aadi_academic_app;
--    ALTER DEFAULT PRIVILEGES FOR ROLE aadi_academic_migrator IN SCHEMA public
--      GRANT USAGE, SELECT ON SEQUENCES TO aadi_academic_app;
--    (repeat with aadi_video_engine_* names in aadi_video_engine)

-- Connection hosts from the other stacks: aadi-postgres:5432 on the aadi-data network.
