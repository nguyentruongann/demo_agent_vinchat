"""add denormalized booking product table

Revision ID: 7f3c2a9d8b10
Revises: 5b7e9c1d2a44
Create Date: 2026-08-18

Một bảng duy nhất cho toàn bộ data/booking/*.json. Các phần lồng được giữ bằng
JSONB và rag_content được tạo sẵn để bước chunk/embed sau này không phải JOIN.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "7f3c2a9d8b10"
down_revision: Union[str, Sequence[str], None] = "5b7e9c1d2a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE core.booking_product (
            id TEXT NOT NULL,
            provider TEXT NOT NULL,
            product_id TEXT NOT NULL,
            ticket_code TEXT,
            booking_code TEXT,
            source_file TEXT,
            source_url TEXT,
            source_language VARCHAR(10),
            source_currency VARCHAR(3),
            source_style TEXT,
            source_tab TEXT,
            source_domain TEXT,
            source_page_type TEXT,
            destination_name TEXT,
            city TEXT,
            province TEXT,
            country TEXT,
            venue_name TEXT,
            service_group TEXT,
            product_name TEXT NOT NULL,
            normalized_product_name TEXT,
            product_type TEXT,
            category TEXT,
            sub_category TEXT,
            status TEXT,
            card_title TEXT,
            short_description TEXT,
            badges JSONB,
            highlights JSONB,
            view_detail_available BOOLEAN,
            select_available BOOLEAN,
            thumbnail_url TEXT,
            images JSONB,
            overview TEXT,
            detail_included JSONB,
            detail_excluded JSONB,
            benefits JSONB,
            experience_description JSONB,
            usage_instructions JSONB,
            important_notes JSONB,
            detail_terms_and_conditions JSONB,
            surcharge_conditions JSONB,
            restrictions JSONB,
            service_locations JSONB,
            operating_information JSONB,
            currency VARCHAR(3),
            pricing_status TEXT,
            price_type TEXT,
            is_dynamic_price BOOLEAN,
            is_from_price BOOLEAN,
            is_approximate_price BOOLEAN,
            display_price TEXT,
            display_original_price TEXT,
            display_discount_text TEXT,
            minimum_price NUMERIC(14, 2),
            maximum_price NUMERIC(14, 2),
            price_variants JSONB,
            is_promotional BOOLEAN,
            promotion_badges JSONB,
            promotion_name TEXT,
            promotion_code TEXT,
            promotion_description TEXT,
            discount_percent NUMERIC(8, 2),
            promotion_start_date TEXT,
            promotion_end_date TEXT,
            customer_conditions JSONB,
            quantity_rules JSONB,
            valid_from TEXT,
            valid_until TEXT,
            validity_text TEXT,
            duration TEXT,
            duration_minutes INTEGER,
            duration_hours INTEGER,
            duration_days INTEGER,
            number_of_uses INTEGER,
            usage_type TEXT,
            same_day_use BOOLEAN,
            time_slot_required BOOLEAN,
            time_slot TEXT,
            entry_time TEXT,
            availability_status TEXT,
            availability_text TEXT,
            sold_out BOOLEAN,
            booking_open BOOLEAN,
            booking_search_url TEXT,
            detail_url TEXT,
            booking_url TEXT,
            cart_url TEXT,
            booking_type TEXT,
            button_text TEXT,
            select_button_available BOOLEAN,
            inclusions JSONB,
            exclusions JSONB,
            policies JSONB,
            surcharges JSONB,
            transportation JSONB,
            food_and_beverage JSONB,
            spa_and_wellness JSONB,
            source_data JSONB,
            validation JSONB,
            rag_content TEXT,
            raw_payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            CONSTRAINT pk_booking_product PRIMARY KEY (id),
            CONSTRAINT uq_booking_product_provider_product_id UNIQUE (provider, product_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_booking_product_ticket_code "
        "ON core.booking_product (ticket_code)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_booking_code "
        "ON core.booking_product (booking_code)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_destination_name "
        "ON core.booking_product (destination_name)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_product_type "
        "ON core.booking_product (product_type)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_minimum_price "
        "ON core.booking_product (minimum_price)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_availability_status "
        "ON core.booking_product (availability_status)"
    )
    op.execute(
        "CREATE INDEX ix_booking_product_raw_payload "
        "ON core.booking_product USING gin (raw_payload)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.booking_product")
