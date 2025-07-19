-- peoples_coin schema.sql
-- Final schema for PostgreSQL 15

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- === User Accounts ===
CREATE TABLE user_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(256) UNIQUE,
    username VARCHAR(64),
    balance NUMERIC(20, 4) DEFAULT 0.0 NOT NULL,
    bio TEXT CHECK (length(bio) <= 120),
    profile_image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === User Wallets ===
CREATE TABLE user_wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_account_id UUID REFERENCES user_accounts(id) ON DELETE CASCADE,
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Goodwill Actions ===
CREATE TABLE goodwill_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    performer_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
    action_type VARCHAR(64) NOT NULL,
    description TEXT,
    contextual_data JSONB,
    loves_value INTEGER NOT NULL CHECK (loves_value >= 0),
    correlation_id UUID,
    status VARCHAR(32) DEFAULT 'PENDING_VERIFICATION',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Chain Blocks ===
CREATE TABLE chain_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_number BIGINT NOT NULL,
    previous_hash VARCHAR(256),
    hash VARCHAR(256) NOT NULL,
    nonce BIGINT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Chain Transactions ===
CREATE TABLE chain_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id UUID REFERENCES chain_blocks(id) ON DELETE CASCADE,
    sender_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
    receiver_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
    amount NUMERIC(20,4) NOT NULL CHECK (amount >= 0),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Consensus Nodes ===
CREATE TABLE consensus_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_identifier VARCHAR(128) UNIQUE NOT NULL,
    status VARCHAR(32) DEFAULT 'ACTIVE',
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Proposals ===
CREATE TABLE proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
    title VARCHAR(256) NOT NULL,
    description TEXT,
    proposal_type VARCHAR(64),
    details JSONB,
    status VARCHAR(32) DEFAULT 'DRAFT',
    vote_start_time TIMESTAMP WITH TIME ZONE,
    vote_end_time TIMESTAMP WITH TIME ZONE,
    required_quorum NUMERIC(5,2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Votes ===
CREATE TABLE votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id UUID REFERENCES proposals(id) ON DELETE CASCADE,
    voter_user_id UUID REFERENCES user_accounts(id) ON DELETE SET NULL,
    vote_choice VARCHAR(16) NOT NULL,
    vote_weight NUMERIC(20,4) NOT NULL CHECK (vote_weight >= 0),
    actual_vote_power NUMERIC(20,4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- === Council Members ===
CREATE TABLE council_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_account_id UUID REFERENCES user_accounts(id) ON DELETE CASCADE,
    role VARCHAR(64) NOT NULL,
    status VARCHAR(32) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

