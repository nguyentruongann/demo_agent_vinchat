"""bridge manual auth/staff schema into Alembic history

Revision ID: c6a0f7b9d2e1
Revises: e1a3d9b2b327
Create Date: 2026-08-12

This revision encodes the schema changes that previously lived only in
src/data_postgre/db/migrations/20260809_auth_staff.sql.  Fresh databases
(such as Railway Postgres) therefore receive the same intermediate schema
that existing local databases had before revision 91e18f0d7446.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c6a0f7b9d2e1"
down_revision: Union[str, Sequence[str], None] = "e1a3d9b2b327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep this intermediate state aligned with the historical
    # 20260809_auth_staff.sql migration.  The following Alembic revisions
    # move these tables to schema app and normalize constraints.
    op.execute(
        """
        ALTER TABLE public.app_user
            ADD COLUMN IF NOT EXISTS phone TEXT,
            ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'customer',
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_app_user_phone
        ON public.app_user(phone)
        WHERE phone IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_user_role
        ON public.app_user(role)
        """
    )
    op.execute(
        """
        UPDATE public.app_user
        SET role = 'staff'
        WHERE is_staff = TRUE
          AND role = 'customer'
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE public.app_user
            ADD CONSTRAINT ck_app_user_role_valid
            CHECK (role IN ('customer','staff','admin'));
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    # Inline UNIQUE is intentional: PostgreSQL names this constraint
    # auth_session_token_hash_key, which the following sync migration
    # (aa3d04a68965) expects to rename.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.auth_session (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL
                REFERENCES public.app_user(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_auth_session_user
        ON public.auth_session(user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_auth_session_expires
        ON public.auth_session(expires_at)
        """
    )

    # These Ticket columns are part of the current ORM but previously came
    # only from the manual SQL migration.
    op.execute(
        """
        ALTER TABLE public.ticket
            ADD COLUMN IF NOT EXISTS contact_name TEXT,
            ADD COLUMN IF NOT EXISTS contact_email TEXT,
            ADD COLUMN IF NOT EXISTS contact_phone TEXT,
            ADD COLUMN IF NOT EXISTS subject TEXT,
            ADD COLUMN IF NOT EXISTS conversation_turns JSONB
        """
    )

    op.execute(
        """
        ALTER TABLE public.ticket
        ADD COLUMN IF NOT EXISTS assigned_to UUID
        REFERENCES public.app_user(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ticket_assigned_to
        ON public.ticket(assigned_to)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ix_ticket_assigned_to")
    op.execute(
        """
        ALTER TABLE public.ticket
            DROP COLUMN IF EXISTS assigned_to,
            DROP COLUMN IF EXISTS conversation_turns,
            DROP COLUMN IF EXISTS subject,
            DROP COLUMN IF EXISTS contact_phone,
            DROP COLUMN IF EXISTS contact_email,
            DROP COLUMN IF EXISTS contact_name
        """
    )

    op.execute("DROP TABLE IF EXISTS public.auth_session CASCADE")

    op.execute(
        """
        ALTER TABLE public.app_user
        DROP CONSTRAINT IF EXISTS ck_app_user_role_valid
        """
    )
    op.execute("DROP INDEX IF EXISTS public.ix_app_user_role")
    op.execute("DROP INDEX IF EXISTS public.uq_app_user_phone")
    op.execute(
        """
        ALTER TABLE public.app_user
            DROP COLUMN IF EXISTS is_active,
            DROP COLUMN IF EXISTS role,
            DROP COLUMN IF EXISTS phone
        """
    )
