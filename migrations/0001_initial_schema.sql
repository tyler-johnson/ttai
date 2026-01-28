-- Initial schema for TastyTrade user authentication

-- Users table - stores TastyTrade account information
CREATE TABLE users (
    id TEXT PRIMARY KEY,              -- TastyTrade account ID
    email TEXT,
    created_at INTEGER DEFAULT (unixepoch())
);

-- User tokens table - stores encrypted TastyTrade OAuth tokens
CREATE TABLE user_tokens (
    user_id TEXT PRIMARY KEY,
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT NOT NULL,
    token_iv TEXT NOT NULL,           -- Initialization vector for AES-GCM
    expires_at INTEGER NOT NULL,      -- Access token expiration timestamp
    updated_at INTEGER DEFAULT (unixepoch()),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- OAuth state table - temporary storage for PKCE flow
CREATE TABLE oauth_state (
    state TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,      -- PKCE code verifier
    redirect_uri TEXT NOT NULL,       -- Where to redirect after auth
    expires_at INTEGER NOT NULL       -- State expires after 10 minutes
);

-- Index for cleaning up expired OAuth states
CREATE INDEX idx_oauth_state_expires ON oauth_state(expires_at);

-- Index for token expiration checks
CREATE INDEX idx_user_tokens_expires ON user_tokens(expires_at);
