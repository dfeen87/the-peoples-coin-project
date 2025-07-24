-- Migration: Add goodwill_coins to user_accounts table
-- Timestamp: 2025-07-23 20:13:51 UTC

-- UP Migration:
-- This section is executed when you apply the migration.
-- It adds the 'goodwill_coins' column with a default value of 0.
ALTER TABLE user_accounts
ADD COLUMN goodwill_coins INTEGER NOT NULL DEFAULT 0;

-- You might also want to add a comment to the column for documentation
COMMENT ON COLUMN user_accounts.goodwill_coins IS 'A non-spendable keepsake token awarded for each verified act of goodwill.';


-- DOWN Migration:
-- This section is executed when you revert or rollback the migration.
-- It safely removes the 'goodwill_coins' column.
ALTER TABLE user_accounts
DROP COLUMN goodwill_coins;
