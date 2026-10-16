from sqlalchemy import inspect

from .extensions import db


def migrate_book_detail_schema():
    columns = {
        "edition_type": "VARCHAR(100)",
        "origin": "VARCHAR(100)",
        "language": "VARCHAR(50)",
        "cover_type": "VARCHAR(100)",
        "distributor": "VARCHAR(150)",
        "publication_year": "VARCHAR(50)",
        "page_count": "VARCHAR(100)",
        "shipping_from": "VARCHAR(100)",
        "size": "VARCHAR(50)",
    }
    connection = db.engine.raw_connection()
    cursor = connection.cursor()
    try:
        existing = {column[1] for column in cursor.execute("PRAGMA table_info(book)")}
        for name, definition in columns.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE book ADD COLUMN {name} {definition}")
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def migrate_social_auth_schema():
    if db.engine.dialect.name != "sqlite":
        inspector = inspect(db.engine)
        if "user" not in inspector.get_table_names():
            return
        columns = {column["name"]: column for column in inspector.get_columns("user")}
        if not columns["password_hash"]["nullable"]:
            raise RuntimeError(
                "Không thể tự chuyển đổi cột mật khẩu trên hệ quản trị này."
            )
        return

    connection = db.engine.raw_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        columns = cursor.execute("PRAGMA table_info(user)").fetchall()
        if not columns:
            connection.commit()
            return
        password_column = next(
            (column for column in columns if column[1] == "password_hash"), None
        )
        if password_column is None:
            raise RuntimeError("Bảng user không có cột password_hash.")
        if not password_column[3]:
            connection.commit()
            return
        cursor.execute(
            """
            CREATE TABLE user_social_auth_new (
                id INTEGER NOT NULL PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(120) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                full_name VARCHAR(100),
                role VARCHAR(20),
                is_active BOOLEAN
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO user_social_auth_new
                (id, username, email, password_hash, full_name, role, is_active)
            SELECT id, username, email, password_hash, full_name, role, is_active
            FROM user
            """
        )
        cursor.execute("DROP TABLE user")
        cursor.execute("ALTER TABLE user_social_auth_new RENAME TO user")
        connection.commit()
    finally:
        try:
            connection.rollback()
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
            connection.close()


def migrate_order_payment_schema():
    if db.engine.dialect.name != "sqlite":
        inspector = inspect(db.engine)
        if "order" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("order")}
            if "payment_method" not in columns:
                raise RuntimeError(
                    "Thiếu cột order.payment_method; cần migration thủ công trên hệ quản trị này."
                )
        return

    connection = db.engine.raw_connection()
    cursor = connection.cursor()
    try:
        columns = cursor.execute('PRAGMA table_info("order")').fetchall()
        if columns and not any(column[1] == "payment_method" for column in columns):
            cursor.execute(
                """
                ALTER TABLE "order"
                ADD COLUMN payment_method VARCHAR(30) NOT NULL
                DEFAULT 'cash_on_delivery'
                """
            )
            connection.commit()
    finally:
        cursor.close()
        connection.close()
