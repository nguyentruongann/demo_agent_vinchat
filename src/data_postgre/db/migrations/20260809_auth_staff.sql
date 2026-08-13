BEGIN;

ALTER TABLE app_user ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'customer';
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_app_user_phone ON app_user(phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_app_user_role ON app_user(role);
UPDATE app_user SET role = 'staff' WHERE is_staff = TRUE AND role = 'customer';

DO $$ BEGIN
    ALTER TABLE app_user ADD CONSTRAINT ck_app_user_role_valid
        CHECK (role IN ('customer','staff','admin'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS auth_session (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_auth_session_user ON auth_session(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_session_expires ON auth_session(expires_at);

ALTER TABLE ticket ADD COLUMN IF NOT EXISTS contact_name TEXT;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS contact_email TEXT;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS contact_phone TEXT;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS subject TEXT;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS conversation_turns JSONB;
ALTER TABLE ticket ADD COLUMN IF NOT EXISTS assigned_to UUID REFERENCES app_user(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_ticket_assigned_to ON ticket(assigned_to);

COMMIT;
