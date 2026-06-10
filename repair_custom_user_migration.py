import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "affirm_care.settings")

import django

django.setup()

from django.db import connection, transaction
from django.utils import timezone


with transaction.atomic():
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if "auth_user" not in tables:
            raise RuntimeError("The legacy auth_user table does not exist.")

        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "auth_user"
            )
        }
        if "account_type" not in columns:
            cursor.execute(
                "ALTER TABLE auth_user "
                "ADD COLUMN account_type varchar(20) NOT NULL DEFAULT 'provider'"
            )

        cursor.execute(
            "UPDATE auth_user SET account_type = 'super_admin' "
            "WHERE is_superuser = TRUE"
        )
        cursor.execute(
            "SELECT email, COUNT(*) FROM auth_user "
            "GROUP BY email HAVING email = '' OR COUNT(*) > 1"
        )
        invalid_emails = cursor.fetchall()
        if invalid_emails:
            raise RuntimeError(
                "Cannot make auth_user.email unique until these values are fixed: "
                f"{invalid_emails}"
            )

        cursor.execute("ALTER TABLE auth_user ALTER COLUMN email SET NOT NULL")
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'auth_user'::regclass
                      AND contype = 'u'
                      AND conkey = ARRAY[
                          (
                              SELECT attnum
                              FROM pg_attribute
                              WHERE attrelid = 'auth_user'::regclass
                                AND attname = 'email'
                          )
                      ]::smallint[]
                ) THEN
                    ALTER TABLE auth_user
                    ADD CONSTRAINT auth_user_email_key UNIQUE (email);
                END IF;
            END
            $$;
            """
        )
        cursor.execute(
            """
            INSERT INTO django_migrations (app, name, applied)
            VALUES ('users', '0001_initial', %s)
            ON CONFLICT DO NOTHING
            """,
            [timezone.now()],
        )

print("Custom user migration history repaired.")
