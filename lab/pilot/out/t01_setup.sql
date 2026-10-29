-- Repro of schema from T-01.task.txt (verbatim structure, nothing added except review_transfer stub
-- and schema USAGE so that app_rw can reach objects at all).
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
