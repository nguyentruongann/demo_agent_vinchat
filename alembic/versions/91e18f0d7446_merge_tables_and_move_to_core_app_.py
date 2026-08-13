"""merge tables and move to core app schemas

Revision ID: 91e18f0d7446
Revises: c6a0f7b9d2e1
Create Date: 2026-08-10 15:05:34.009403
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "91e18f0d7446"
down_revision: Union[str, Sequence[str], None] = "c6a0f7b9d2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CORE_TABLES = [
    "amenity",
    "brand",
    "destination",
    "ingest_run",
    "media",
    "data_quality_issue",
    "destination_alias",
    "source",
    "complex",
    "entity_source",
    "faq",
    "org_info",
    "page_link",
    "policy_document",
    "promotion",
    "attraction",
    "destination_highlight",
    "golf_course",
    "policy_block",
    "policy_section",
    "promotion_benefit",
    "promotion_block",
    "promotion_code",
    "promotion_destination",
    "promotion_relation",
    "promotion_section",
    "promotion_term",
    "property",
    "dining_service",
    "golf_feature",
    "mice_venue",
    "org_highlight",
    "promotion_property_raw",
    "room",
    "mice_room",
    "mice_room_capacity",
]


APP_TABLES = [
    "app_user",
    "auth_session",
    "session",
    "event_log",
    "message",
    "message_citation",
    "message_feedback",
    "ticket",
]


def upgrade() -> None:
    """Gộp 5 bảng legacy và chuyển DB từ public sang core/app."""

    # ============================================================
    # 1. TẠO SCHEMA
    # ============================================================
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    # ============================================================
    # 2. room_amenity -> room.amenity_ids
    # ============================================================
    op.execute(
        """
        ALTER TABLE public.room
        ADD COLUMN IF NOT EXISTS amenity_ids TEXT[]
        """
    )

    op.execute(
        """
        UPDATE public.room AS r
        SET amenity_ids = src.amenity_ids
        FROM (
            SELECT
                room_id,
                array_agg(
                    amenity_id
                    ORDER BY amenity_id
                ) AS amenity_ids
            FROM public.room_amenity
            GROUP BY room_id
        ) AS src
        WHERE r.id = src.room_id
        """
    )

    # ============================================================
    # 3. promotion_tag -> promotion.tags
    #
    # Kết quả:
    # {
    #   "promotion_type": ["combo_package", ...],
    #   "service": [...],
    #   ...
    # }
    # ============================================================
    op.execute(
        """
        ALTER TABLE public.promotion
        ADD COLUMN IF NOT EXISTS tags JSONB
        """
    )

    op.execute(
        """
        UPDATE public.promotion AS p
        SET tags = src.tags
        FROM (
            SELECT
                promotion_id,
                jsonb_object_agg(
                    tag_type,
                    tag_values
                ) AS tags
            FROM (
                SELECT
                    promotion_id,
                    tag_type,
                    jsonb_agg(
                        tag_value
                        ORDER BY tag_value
                    ) AS tag_values
                FROM public.promotion_tag
                GROUP BY promotion_id, tag_type
            ) AS grouped_tags
            GROUP BY promotion_id
        ) AS src
        WHERE p.id = src.promotion_id
        """
    )

    # ============================================================
    # 4. attraction_itinerary_day -> attraction.itinerary
    # ============================================================
    op.execute(
        """
        ALTER TABLE public.attraction
        ADD COLUMN IF NOT EXISTS itinerary JSONB
        """
    )

    op.execute(
        """
        UPDATE public.attraction AS a
        SET itinerary = src.itinerary
        FROM (
            SELECT
                attraction_id,
                jsonb_agg(
                    jsonb_build_object(
                        'day_number', day_number,
                        'heading', heading,
                        'text', text,
                        'activities', activities
                    )
                    ORDER BY day_number
                ) AS itinerary
            FROM public.attraction_itinerary_day
            GROUP BY attraction_id
        ) AS src
        WHERE a.id = src.attraction_id
        """
    )

    # ============================================================
    # 5. promotion_step -> promotion_term(kind='step')
    #
    # Constraint cũ:
    # term / combination / contact
    #
    # Constraint mới:
    # term / combination / contact / step
    # ============================================================
    op.execute(
        """
        ALTER TABLE public.promotion_term
        DROP CONSTRAINT IF EXISTS ck_promotion_term_kind_valid
        """
    )

    op.execute(
        """
        ALTER TABLE public.promotion_term
        ADD CONSTRAINT ck_promotion_term_kind_valid
        CHECK (
            kind IN (
                'term',
                'combination',
                'contact',
                'step'
            )
        )
        """
    )

    op.execute(
        """
        INSERT INTO public.promotion_term (
            id,
            promotion_id,
            kind,
            ord,
            text,
            created_at,
            updated_at
        )
        SELECT
            ps.id,
            ps.promotion_id,
            'step',
            ps.ord,
            ps.text,
            ps.created_at,
            ps.updated_at
        FROM public.promotion_step AS ps
        ON CONFLICT (id) DO NOTHING
        """
    )

    # Model mới có unique:
    # promotion_id + kind + ord
    op.execute(
        """
        ALTER TABLE public.promotion_term
        ADD CONSTRAINT uq_promotion_term_ord
        UNIQUE (promotion_id, kind, ord)
        """
    )

    # ============================================================
    # 6. golf_course_map -> golf_feature(kind='map')
    #
    # golf_course_map.course_type -> golf_feature.variant
    # golf_course_map.map_name    -> golf_feature.title
    # golf_course_map.map_url     -> golf_feature.image_url
    # ============================================================

    # Model mới có thêm variant.
    op.execute(
        """
        ALTER TABLE public.golf_feature
        ADD COLUMN IF NOT EXISTS variant TEXT
        """
    )

    # sort_order đã có ở migration cũ,
    # nhưng IF NOT EXISTS giúp migration an toàn hơn.
    op.execute(
        """
        ALTER TABLE public.golf_feature
        ADD COLUMN IF NOT EXISTS sort_order INTEGER
        """
    )

    # Constraint cũ chưa cho phép map.
    op.execute(
        """
        ALTER TABLE public.golf_feature
        DROP CONSTRAINT IF EXISTS ck_golf_feature_kind_valid
        """
    )

    # Đúng theo core.py mới:
    # feature / award / amenity / experience / map
    op.execute(
        """
        ALTER TABLE public.golf_feature
        ADD CONSTRAINT ck_golf_feature_kind_valid
        CHECK (
            kind IN (
                'feature',
                'award',
                'amenity',
                'experience',
                'map'
            )
        )
        """
    )

    op.execute(
        """
        INSERT INTO public.golf_feature (
            id,
            course_id,
            kind,
            title,
            description,
            image_url,
            detail_url,
            variant,
            sort_order,
            content_hash,
            is_active,
            source_id,
            ingest_run_id,
            created_at,
            updated_at
        )
        SELECT
            gm.id,
            gm.course_id,
            'map',
            COALESCE(
                gm.map_name,
                gm.course_type,
                'Course Map'
            ),
            NULL,
            gm.map_url,
            NULL,
            gm.course_type,
            NULL,
            gm.content_hash,
            gm.is_active,
            gm.source_id,
            gm.ingest_run_id,
            gm.created_at,
            gm.updated_at
        FROM public.golf_course_map AS gm
        ON CONFLICT (id) DO NOTHING
        """
    )

    # ============================================================
    # 7. CHUYỂN 36 BẢNG CORE
    # public.xxx -> core.xxx
    # ============================================================
    for table_name in CORE_TABLES:
        op.execute(
            f'ALTER TABLE public."{table_name}" SET SCHEMA core'
        )

    # ============================================================
    # 8. CHUYỂN 8 BẢNG APP
    # public.xxx -> app.xxx
    # ============================================================
    for table_name in APP_TABLES:
        op.execute(
            f'ALTER TABLE public."{table_name}" SET SCHEMA app'
        )

    # ============================================================
    # 9. TẠO INDEX MỚI CHO CÁC FIELD ĐÃ GỘP
    # ============================================================

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_room_amenity_ids
        ON core.room
        USING GIN (amenity_ids)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_promotion_tags
        ON core.promotion
        USING GIN (tags)
        """
    )

    # ============================================================
    # 10. KHÔNG DROP 5 BẢNG LEGACY Ở MIGRATION NÀY
    #
    # Chúng vẫn ở public để đối chiếu dữ liệu:
    #
    # public.room_amenity
    # public.promotion_tag
    # public.attraction_itinerary_day
    # public.promotion_step
    # public.golf_course_map
    #
    # Sau khi verify dữ liệu mới đúng mới drop.
    # ============================================================


def downgrade() -> None:
    """Đưa bảng trở về public và hoàn tác dữ liệu gộp."""

    # ============================================================
    # 1. MOVE APP BACK TO PUBLIC
    # ============================================================
    for table_name in reversed(APP_TABLES):
        op.execute(
            f'ALTER TABLE app."{table_name}" SET SCHEMA public'
        )

    # ============================================================
    # 2. MOVE CORE BACK TO PUBLIC
    # ============================================================
    for table_name in reversed(CORE_TABLES):
        op.execute(
            f'ALTER TABLE core."{table_name}" SET SCHEMA public'
        )

    # ============================================================
    # 3. XÓA ROW MAP ĐÃ COPY SANG golf_feature
    # ============================================================
    op.execute(
        """
        DELETE FROM public.golf_feature AS gf
        USING public.golf_course_map AS gm
        WHERE gf.id = gm.id
          AND gf.kind = 'map'
        """
    )

    # Restore constraint cũ.
    op.execute(
        """
        ALTER TABLE public.golf_feature
        DROP CONSTRAINT IF EXISTS ck_golf_feature_kind_valid
        """
    )

    op.execute(
        """
        ALTER TABLE public.golf_feature
        ADD CONSTRAINT ck_golf_feature_kind_valid
        CHECK (
            kind IN (
                'feature',
                'award',
                'amenity',
                'experience'
            )
        )
        """
    )

    op.execute(
        """
        ALTER TABLE public.golf_feature
        DROP COLUMN IF EXISTS variant
        """
    )

    # ============================================================
    # 4. XÓA promotion_step ĐÃ COPY SANG promotion_term
    # ============================================================
    op.execute(
        """
        DELETE FROM public.promotion_term AS pt
        USING public.promotion_step AS ps
        WHERE pt.id = ps.id
          AND pt.kind = 'step'
        """
    )

    op.execute(
        """
        ALTER TABLE public.promotion_term
        DROP CONSTRAINT IF EXISTS uq_promotion_term_ord
        """
    )

    op.execute(
        """
        ALTER TABLE public.promotion_term
        DROP CONSTRAINT IF EXISTS ck_promotion_term_kind_valid
        """
    )

    op.execute(
        """
        ALTER TABLE public.promotion_term
        ADD CONSTRAINT ck_promotion_term_kind_valid
        CHECK (
            kind IN (
                'term',
                'combination',
                'contact'
            )
        )
        """
    )

    # ============================================================
    # 5. DROP INDEX MỚI
    # ============================================================
    op.execute(
        """
        DROP INDEX IF EXISTS public.ix_room_amenity_ids
        """
    )

    op.execute(
        """
        DROP INDEX IF EXISTS public.ix_promotion_tags
        """
    )

    # ============================================================
    # 6. XÓA CÁC COLUMN ĐÃ GỘP
    #
    # Dữ liệu nguồn vẫn còn nguyên trong 5 bảng legacy.
    # ============================================================
    op.execute(
        """
        ALTER TABLE public.room
        DROP COLUMN IF EXISTS amenity_ids
        """
    )

    op.execute(
        """
        ALTER TABLE public.promotion
        DROP COLUMN IF EXISTS tags
        """
    )

    op.execute(
        """
        ALTER TABLE public.attraction
        DROP COLUMN IF EXISTS itinerary
        """
    )

    # ============================================================
    # 7. XÓA SCHEMA RỖNG
    # ============================================================
    op.execute("DROP SCHEMA IF EXISTS app")
    op.execute("DROP SCHEMA IF EXISTS core")