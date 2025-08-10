-- peoples_coin - Final Production Schema (Lex-polished)
-- PostgreSQL 15+
-- Purpose: stable production-ready schema with immutability for ledger entries,
-- indexes for FK columns, soft deletes for content tables, and consistent timestamp triggers.

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--------------------------------------------------------------------------------
-- === ENUM TYPES ===
--------------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE goodwill_status AS ENUM ('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE proposal_status AS ENUM ('DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE vote_option AS ENUM ('FOR', 'AGAINST', 'ABSTAIN');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE notification_type AS ENUM (
        'PROPOSAL_UPDATE', 'VOTE_RESULT', 'NEW_COMMENT', 'GOODWILL_VERIFIED',
        'GOODWILL_REJECTED', 'FUNDS_RECEIVED', 'MENTION', 'BOUNTY_COMPLETED'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE goodwill_transaction_type AS ENUM (
        'EARNED_ACTION', 'SPENT_ON_FEATURE', 'ADMIN_ADJUSTMENT', 'REWARD', 'BOUNTY_PAYOUT'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE audited_action AS ENUM (
        'USER_LOGIN', 'USER_UPDATE_EMAIL', 'ROLE_GRANTED', 'ROLE_REVOKED',
        'PROPOSAL_STATUS_CHANGED', 'GOODWILL_ACTION_VERIFIED', 'SETTINGS_CHANGED',
        'CONTENT_REPORT_REVIEWED'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE reportable_entity_type AS ENUM ('PROPOSAL', 'COMMENT', 'GOODWILL_ACTION', 'USER_ACCOUNT');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE report_status AS ENUM ('PENDING_REVIEW', 'ACTION_TAKEN', 'DISMISSED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

--------------------------------------------------------------------------------
-- === UTILITY: updated_at trigger ===
--------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

--------------------------------------------------------------------------------
-- === UTILITY: Prevent modifications on immutable ledger entries ===
--------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION prevent_ledger_modifications()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'Ledger entries are immutable and cannot be updated or deleted';
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

--------------------------------------------------------------------------------
-- === CORE TABLES ===
--------------------------------------------------------------------------------

-- User Accounts
CREATE TABLE IF NOT EXISTS user_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(256) UNIQUE NULL,
    username VARCHAR(64) NULL,
    balance NUMERIC(20, 8) NOT NULL DEFAULT 0.0 CHECK (balance >= 0),
    goodwill_coins INTEGER NOT NULL DEFAULT 0 CHECK (goodwill_coins >= 0),
    bio TEXT NULL CHECK (char_length(bio) <= 120),
    profile_image_url TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON user_accounts(email);
CREATE INDEX IF NOT EXISTS idx_user_accounts_username ON user_accounts(username);
CREATE INDEX IF NOT EXISTS idx_user_accounts_deleted_at ON user_accounts(deleted_at);
CREATE TRIGGER trg_user_accounts_updated_at BEFORE UPDATE ON user_accounts FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- User Wallets
CREATE TABLE IF NOT EXISTS user_wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    public_address VARCHAR(42) NOT NULL UNIQUE,
    blockchain_network VARCHAR(50) NOT NULL DEFAULT 'Ethereum Mainnet',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    encrypted_private_key TEXT NULL, -- Application must encrypt BEFORE storing
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_wallets_user_id ON user_wallets(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_wallets_unique_primary_wallet ON user_wallets (user_id, is_primary) WHERE is_primary = TRUE;
CREATE TRIGGER trg_user_wallets_updated_at BEFORE UPDATE ON user_wallets FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
COMMENT ON COLUMN user_wallets.encrypted_private_key IS 'Stores application-level encrypted private key as text. MUST be encrypted BEFORE storing.';

-- User Token Assets (NFTs)
CREATE TABLE IF NOT EXISTS user_token_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_account_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    wallet_id UUID NOT NULL REFERENCES user_wallets(id) ON DELETE CASCADE,
    blockchain_network VARCHAR(50) NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    token_id NUMERIC(78, 0) NOT NULL,
    metadata JSONB NULL,
    last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT unique_token_instance UNIQUE (blockchain_network, contract_address, token_id)
);
CREATE INDEX IF NOT EXISTS idx_user_token_assets_user_account_id ON user_token_assets(user_account_id);
CREATE INDEX IF NOT EXISTS idx_user_token_assets_wallet_id ON user_token_assets(wallet_id);
CREATE TRIGGER trg_user_token_assets_updated_at BEFORE UPDATE ON user_token_assets FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
COMMENT ON TABLE user_token_assets IS 'Tracks ownership of specific, non-fungible tokens for each user.';

-- Goodwill Actions
CREATE TABLE IF NOT EXISTS goodwill_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    performer_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    action_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    contextual_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    loves_value INTEGER NOT NULL DEFAULT 0 CHECK (loves_value >= 0),
    resonance_score DOUBLE PRECISION NULL,
    status goodwill_status NOT NULL DEFAULT 'PENDING_VERIFICATION',
    processed_at TIMESTAMP WITH TIME ZONE NULL,
    blockchain_tx_hash VARCHAR(66) UNIQUE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX IF NOT EXISTS idx_goodwill_actions_performer_user_id ON goodwill_actions(performer_user_id);
CREATE INDEX IF NOT EXISTS idx_goodwill_actions_status ON goodwill_actions(status);
CREATE INDEX IF NOT EXISTS idx_goodwill_actions_deleted_at ON goodwill_actions(deleted_at);
CREATE TRIGGER trg_goodwill_actions_updated_at BEFORE UPDATE ON goodwill_actions FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

--------------------------------------------------------------------------------
-- === LEDGER & CHAIN TABLES ===
--------------------------------------------------------------------------------

-- Ledger Entries (immutable)
CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blockchain_tx_hash VARCHAR(66) UNIQUE NOT NULL,
    goodwill_action_id UUID UNIQUE NULL REFERENCES goodwill_actions(id) ON DELETE SET NULL,
    transaction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL CHECK (amount >= 0),
    token_symbol VARCHAR(10) NOT NULL,
    sender_address VARCHAR(42) NOT NULL,
    receiver_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    block_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
    meta_data JSONB NULL DEFAULT '{}'::jsonb,
    initiator_user_id UUID NULL REFERENCES user_accounts(id),
    receiver_user_id UUID NULL REFERENCES user_accounts(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
    -- Intentionally no updated_at: entries are immutable. (If you prefer an updated_at for admin annotations, add it intentionally.)
);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_block_number ON ledger_entries(block_number);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_sender_address ON ledger_entries(sender_address);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_receiver_address ON ledger_entries(receiver_address);
-- Make ledger entries immutable: prevent UPDATE and DELETE
CREATE TRIGGER trg_prevent_ledger_update_delete
BEFORE UPDATE OR DELETE ON ledger_entries
FOR EACH ROW EXECUTE PROCEDURE prevent_ledger_modifications();

-- Goodwill Ledger (off-chain coin audit trail)
CREATE TABLE IF NOT EXISTS goodwill_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    transaction_type goodwill_transaction_type NOT NULL,
    amount INTEGER NOT NULL,
    balance_after_transaction INTEGER NOT NULL,
    description TEXT NOT NULL,
    related_goodwill_action_id UUID NULL REFERENCES goodwill_actions(id) ON DELETE SET NULL,
    meta_data JSONB NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_goodwill_ledger_user_id ON goodwill_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_goodwill_ledger_related_action ON goodwill_ledger(related_goodwill_action_id);

-- Chain Blocks (blockchain indexing)
CREATE TABLE IF NOT EXISTS chain_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    height INTEGER NOT NULL UNIQUE CHECK (height >= 0),
    previous_hash BYTEA NULL,
    current_hash BYTEA NOT NULL UNIQUE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    miner VARCHAR(64) NULL,
    tx_count INTEGER NOT NULL DEFAULT 0 CHECK (tx_count >= 0),
    goodwill_actions_count INTEGER NOT NULL DEFAULT 0 CHECK (goodwill_actions_count >= 0),
    proposals_count INTEGER NOT NULL DEFAULT 0 CHECK (proposals_count >= 0),
    ledger_total_amount NUMERIC(20, 8) NOT NULL DEFAULT 0.0,
    block_summary JSONB NULL DEFAULT '{}'::jsonb,
    CONSTRAINT check_hash_length CHECK (octet_length(current_hash) = 32 AND (previous_hash IS NULL OR octet_length(previous_hash) = 32))
);
CREATE INDEX IF NOT EXISTS idx_chain_blocks_height ON chain_blocks(height);
CREATE INDEX IF NOT EXISTS idx_chain_blocks_timestamp ON chain_blocks(timestamp);
CREATE TRIGGER trg_chain_blocks_updated_at BEFORE UPDATE ON chain_blocks FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

--------------------------------------------------------------------------------
-- === GOVERNANCE & COMMUNITY ===
--------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status proposal_status NOT NULL DEFAULT 'DRAFT',
    vote_start_time TIMESTAMP WITH TIME ZONE NULL,
    vote_end_time TIMESTAMP WITH TIME ZONE NULL,
    required_quorum NUMERIC(5,2) NOT NULL DEFAULT 0,
    proposal_type VARCHAR(100) NOT NULL,
    details JSONB NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP WITH TIME ZONE NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_proposer_user_id ON proposals(proposer_user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_deleted_at ON proposals(deleted_at);
CREATE TRIGGER trg_proposals_updated_at BEFORE UPDATE ON proposals FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TABLE IF NOT EXISTS votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voter_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    proposal_id UUID NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    vote_value vote_option NOT NULL,
    rationale TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT unique_voter_proposal UNIQUE (voter_user_id, proposal_id)
);
CREATE INDEX IF NOT EXISTS idx_votes_voter_user_id ON votes(voter_user_id);
CREATE INDEX IF NOT EXISTS idx_votes_proposal_id ON votes(proposal_id);

CREATE TABLE IF NOT EXISTS council_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES user_accounts(id) ON DELETE CASCADE,
    role VARCHAR(100) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    end_date TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT check_end_date_after_start_date CHECK (end_date IS NULL OR end_date > start_date)
);
CREATE TRIGGER trg_council_members_updated_at BEFORE UPDATE ON council_members FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TABLE IF NOT EXISTS bounties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    related_proposal_id UUID NULL REFERENCES proposals(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status proposal_status NOT NULL DEFAULT 'ACTIVE',
    reward_amount NUMERIC(20, 8) NOT NULL,
    reward_token_symbol VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NULL,
    max_participants INTEGER NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_bounties_updated_at BEFORE UPDATE ON bounties FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

--------------------------------------------------------------------------------
-- === SOCIAL & INTERACTION ===
--------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS followers (
    follower_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    followed_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_user_id, followed_user_id),
    CONSTRAINT chk_no_self_follow CHECK (follower_user_id <> followed_user_id)
);

CREATE TABLE IF NOT EXISTS action_loves (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    goodwill_action_id UUID NOT NULL REFERENCES goodwill_actions(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT unique_user_action_love UNIQUE (user_id, goodwill_action_id)
);
CREATE INDEX IF NOT EXISTS idx_action_loves_goodwill_action_id ON action_loves(goodwill_action_id);

CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    proposal_id UUID NULL REFERENCES proposals(id) ON DELETE CASCADE,
    goodwill_action_id UUID NULL REFERENCES goodwill_actions(id) ON DELETE CASCADE,
    parent_comment_id UUID NULL REFERENCES comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL CHECK (char_length(content) > 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT chk_comment_has_target CHECK (
        (proposal_id IS NOT NULL AND goodwill_action_id IS NULL) OR
        (proposal_id IS NULL AND goodwill_action_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_comments_author_user_id ON comments(author_user_id);
CREATE INDEX IF NOT EXISTS idx_comments_proposal_id ON comments(proposal_id);
CREATE INDEX IF NOT EXISTS idx_comments_goodwill_action_id ON comments(goodwill_action_id);
CREATE TRIGGER trg_comments_updated_at BEFORE UPDATE ON comments FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL CHECK (char_length(name) > 0)
);

CREATE TABLE IF NOT EXISTS goodwill_action_tags (
    goodwill_action_id UUID NOT NULL REFERENCES goodwill_actions(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (goodwill_action_id, tag_id)
);

CREATE TABLE IF NOT EXISTS proposal_tags (
    proposal_id UUID NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (proposal_id, tag_id)
);

--------------------------------------------------------------------------------
-- === SYSTEM, SECURITY & AUDIT ===
--------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(64) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    last_used_at TIMESTAMP WITH TIME ZONE NULL,
    expires_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_api_keys_updated_at BEFORE UPDATE ON api_keys FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    type notification_type NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NULL,
    link_url TEXT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_user_id ON notifications(recipient_user_id);

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT NOT NULL,
    last_updated_by_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_system_settings_updated_at BEFORE UPDATE ON system_settings FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    action_type audited_action NOT NULL,
    target_entity_id VARCHAR(255) NULL,
    details JSONB NULL,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_user_id ON audit_log(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_type ON audit_log(action_type);

CREATE TABLE IF NOT EXISTS content_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    entity_type reportable_entity_type NOT NULL,
    entity_id UUID NOT NULL,
    reason TEXT NOT NULL CHECK (char_length(reason) > 10),
    status report_status NOT NULL DEFAULT 'PENDING_REVIEW',
    reviewer_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    resolution_notes TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_content_reports_updated_at BEFORE UPDATE ON content_reports FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

--------------------------------------------------------------------------------
-- === FINAL NOTES / BEST PRACTICES (short) ===
--------------------------------------------------------------------------------
-- 1) Run this on a fresh DB or carefully diff/apply changes in a staging environment first.
-- 2) Back up your data before making destructive changes.
-- 3) If you use Alembic/Flask-Migrate, generate migrations from your SQLAlchemy models based
--    on this canonical schema to keep migrations consistent.
-- 4) Ledger entries are immutable (trigger prevents UPDATE/DELETE). If you need admin annotations,
--    create a separate table (e.g. ledger_entry_notes) that references ledger_entries.id.
-- 5) Keep database credentials secure and use Cloud SQL Proxy or private IP for cloud deployments.

-- END

