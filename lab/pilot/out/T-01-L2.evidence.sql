-- T-01 evidence transcript (PostgreSQL 17.2, local cluster 127.0.0.1:54329)
-- Question q1: which principals can change sample2.accounts.balance without calling
-- sample2.review_transfer()?
-- Schema is reproduced verbatim from lab/pilot/T-01.task.txt. Only additions: USAGE on schema
-- (otherwise no role can touch anything), a review_transfer() stub, and INSERT of two rows.
-- Run: psql -h 127.0.0.1 -p 54329 -U postgres -v ON_ERROR_STOP=0 -f T-01-L2.evidence.sql

\set ECHO all

DROP DATABASE IF EXISTS t01_probe;
CREATE DATABASE t01_probe;
\connect t01_probe

CREATE SCHEMA sample2;
CREATE TABLE sample2.accounts(id bigserial PRIMARY KEY, balance numeric NOT NULL DEFAULT 0);
INSERT INTO sample2.accounts(balance) VALUES (100), (200);

CREATE VIEW sample2.accounts_v AS SELECT id, balance FROM sample2.accounts;

CREATE FUNCTION sample2.accounts_v_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE sample2.accounts SET balance = NEW.balance WHERE id = NEW.id;
  RETURN NEW;
END $$;

CREATE FUNCTION sample2.set_balance(p_id bigint, p_amount numeric) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  UPDATE sample2.accounts SET balance = p_amount WHERE id = p_id;
END $$;

CREATE FUNCTION sample2.review_transfer(p_from bigint, p_to bigint, p_amount numeric) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  UPDATE sample2.accounts SET balance = balance - p_amount WHERE id = p_from;
  UPDATE sample2.accounts SET balance = balance + p_amount WHERE id = p_to;
END $$;

CREATE TRIGGER accounts_v_write INSTEAD OF UPDATE ON sample2.accounts_v
  FOR EACH ROW EXECUTE FUNCTION sample2.accounts_v_update();

GRANT USAGE ON SCHEMA sample2 TO app_rw;
GRANT SELECT, UPDATE ON sample2.accounts_v TO app_rw;
GRANT EXECUTE ON FUNCTION sample2.set_balance(bigint, numeric) TO app_rw;

\echo '=== T1: app_rw -> direct UPDATE sample2.accounts  (EXPECT: permission denied)'
SET ROLE app_rw;
UPDATE sample2.accounts SET balance = 999 WHERE id = 1;
RESET ROLE;

\echo '=== T2: app_rw -> SELECT sample2.set_balance(1, 555)  (EXPECT: succeeds, no review_transfer)'
SET ROLE app_rw;
SELECT sample2.set_balance(1, 555);
RESET ROLE;

\echo '=== T3: app_rw -> UPDATE sample2.accounts_v  (EXPECT: permission denied on table accounts)'
SET ROLE app_rw;
UPDATE sample2.accounts_v SET balance = 777 WHERE id = 2;
RESET ROLE;

\echo '=== T4: state after T1-T3 (EXPECT: id1=555, id2=200)'
SELECT id, balance FROM sample2.accounts ORDER BY id;

\echo '=== T5: default function privileges (EXPECT: PUBLIC has EXECUTE on both functions)'
SELECT r AS role, has_function_privilege(r, 'sample2.set_balance(bigint,numeric)', 'EXECUTE') AS can_set_balance,
       has_function_privilege(r, 'sample2.review_transfer(bigint,bigint,numeric)', 'EXECUTE') AS can_review
FROM unnest(ARRAY['app_rw','app_r0','public']) AS r;

\echo '=== T6: role app_r0 with NO grant, only schema USAGE -> set_balance(2, 4242)  (EXPECT: succeeds)'
GRANT USAGE ON SCHEMA sample2 TO app_r0;
SET ROLE app_r0;
SELECT sample2.set_balance(2, 4242);
RESET ROLE;
SELECT id, balance FROM sample2.accounts ORDER BY id;

\echo '=== T7: COUNTERFACTUAL: accounts_v_update() made SECURITY DEFINER'
\echo '===     app_rw -> UPDATE sample2.accounts_v  (EXPECT: succeeds -- i.e. the view path opens)'
ALTER FUNCTION sample2.accounts_v_update() SECURITY DEFINER;
SET ROLE app_rw;
UPDATE sample2.accounts_v SET balance = 31337 WHERE id = 2;
RESET ROLE;
SELECT id, balance FROM sample2.accounts ORDER BY id;

\echo '=== T8: back to SECURITY INVOKER, trigger dropped (plain updatable view)'
\echo '===     app_rw -> UPDATE sample2.accounts_v  (EXPECT: succeeds -- plain view uses owner rights)'
ALTER FUNCTION sample2.accounts_v_update() SECURITY INVOKER;
DROP TRIGGER accounts_v_write ON sample2.accounts_v;
SET ROLE app_rw;
UPDATE sample2.accounts_v SET balance = 11 WHERE id = 1;
RESET ROLE;
SELECT id, balance FROM sample2.accounts ORDER BY id;

\echo '=== T9: trigger restored as given (SECURITY INVOKER), same statement'
\echo '===     (EXPECT: permission denied -- the trigger, not the view, closes the path)'
CREATE TRIGGER accounts_v_write INSTEAD OF UPDATE ON sample2.accounts_v
  FOR EACH ROW EXECUTE FUNCTION sample2.accounts_v_update();
SET ROLE app_rw;
UPDATE sample2.accounts_v SET balance = 22 WHERE id = 1;
RESET ROLE;

\echo '=== T10: final state (EXPECT: id1=11, id2=31337)'
SELECT id, balance FROM sample2.accounts ORDER BY id;

\connect postgres
DROP DATABASE t01_probe;
\echo '=== probe database dropped; cluster left as found'
