-- peoples_coin schema.sql
-- Final polished schema for PostgreSQL 15, with explicit nullability

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- === ENUM Types ===
DO $$ BEGIN
    CREATE TYPE goodwill_status AS ENUM ('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE proposal_status AS ENUM ('DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- === HELPER FUNCTION: auto-update updated_at timestamp ===
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';


-- === User Accounts ===
CREATE TABLE user_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(256) UNIQUE NULL,
    username VARCHAR(64) NULL,
    balance NUMERIC(20, 4) NOT NULL DEFAULT 0.0,
    goodwill_coins INTEGER NOT NULL DEFAULT 0, -- Added: Non-spendable coins for goodwill acts
    bio TEXT NULL CHECK (length(bio) <= 120),
    profile_image_url TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_accounts_email ON user_accounts(email);
CREATE INDEX IF NOT EXISTS idx_user_accounts_username ON user_accounts(username);
CREATE TRIGGER update_user_accounts_updated_at BEFORE UPDATE ON user_accounts FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === API Keys ===
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(64) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    last_used_at TIMESTAMP WITH TIME ZONE NULL,
    expires_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE TRIGGER update_api_keys_updated_at BEFORE UPDATE ON api_keys FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === User Wallets ===
CREATE TABLE user_wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    public_address VARCHAR(42) NOT NULL UNIQUE,
    blockchain_network VARCHAR(50) NOT NULL DEFAULT 'Ethereum Mainnet',
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_user_wallets_unique_primary_wallet ON user_wallets (user_id, is_primary) WHERE is_primary = TRUE;
CREATE TRIGGER update_user_wallets_updated_at BEFORE UPDATE ON user_wallets FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Goodwill Actions ===
CREATE TABLE goodwill_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    performer_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    action_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    contextual_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    loves_value INTEGER NOT NULL DEFAULT 0 CHECK (loves_value >= 0),
    resonance_score FLOAT NULL,
    status goodwill_status NOT NULL DEFAULT 'PENDING_VERIFICATION',
    processed_at TIMESTAMP WITH TIME ZONE NULL,
    blockchain_tx_hash VARCHAR(66) UNIQUE NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_goodwill_actions_performer_user_id ON goodwill_actions(performer_user_id);
CREATE INDEX IF NOT EXISTS idx_goodwill_actions_action_type ON goodwill_actions(action_type);
CREATE TRIGGER update_goodwill_actions_updated_at BEFORE UPDATE ON goodwill_actions FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Ledger Entries ===
CREATE TABLE ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blockchain_tx_hash VARCHAR(66) UNIQUE NOT NULL,
    goodwill_action_id UUID UNIQUE NULL REFERENCES goodwill_actions(id) ON DELETE SET NULL,
    transaction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    token_symbol VARCHAR(10) NOT NULL DEFAULT 'GOODWILL',
    sender_address VARCHAR(42) NOT NULL,
    receiver_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    block_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED',
    meta_data JSONB NULL DEFAULT '{}'::jsonb,
    initiator_user_id UUID NULL REFERENCES user_accounts(id),
    receiver_user_id UUID NULL REFERENCES user_accounts(id),
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_sender_address ON ledger_entries(sender_address);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_receiver_address ON ledger_entries(receiver_address);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_transaction_type ON ledger_entries(transaction_type);
CREATE TRIGGER update_ledger_entries_updated_at BEFORE UPDATE ON ledger_entries FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Chain Blocks ===
CREATE TABLE chain_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_hash VARCHAR(128) UNIQUE NOT NULL,
    previous_hash VARCHAR(128) NULL,
    data JSONB NOT NULL,
    height INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chain_blocks_height ON chain_blocks(height);
CREATE TRIGGER update_chain_blocks_updated_at BEFORE UPDATE ON chain_blocks FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Proposals ===
CREATE TABLE proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status proposal_status NOT NULL DEFAULT 'DRAFT',
    vote_start_time TIMESTAMP WITH TIME ZONE NULL,
    vote_end_time TIMESTAMP WITH TIME ZONE NULL,
    required_quorum NUMERIC(5, 2) NOT NULL DEFAULT 0,
    proposal_type VARCHAR(100) NOT NULL,
    details JSONB NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_proposals_proposer_user_id ON proposals(proposer_user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_proposal_type ON proposals(proposal_type);
CREATE TRIGGER update_proposals_updated_at BEFORE UPDATE ON proposals FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Votes ===
CREATE TABLE votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    voter_user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
    proposal_id UUID NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    vote_value VARCHAR(10) NOT NULL,
    rationale TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    CONSTRAINT unique_voter_proposal UNIQUE (voter_user_id, proposal_id)
);
CREATE TRIGGER update_votes_updated_at BEFORE UPDATE ON votes FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === Council Members ===
CREATE TABLE council_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES user_accounts(id) ON DELETE CASCADE,
    role VARCHAR(100) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    end_date TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT now(),
    CONSTRAINT check_end_date_after_start_date CHECK (end_date IS NULL OR end_date > start_date)
);
CREATE INDEX IF NOT EXISTS idx_council_members_role ON council_members(role);
CREATE TRIGGER update_council_members_updated_at BEFORE UPDATE ON council_members FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();


-- === System Controller ===
CREATE TABLE IF NOT EXISTS controller_actions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL, -- Added Line
    recommendations JSONB,
    actions_taken JSONB
);
CREATE INDEX IF NOT EXISTS idx_controller_actions_user_id ON controller_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_controller_actions_timestamp ON controller_actions(timestamp);
