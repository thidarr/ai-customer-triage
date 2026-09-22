import psycopg

from app.config import ConfigurationError, get_database_url
from app.schemas import CustomerRequest, NotificationStatus, TriageResult

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS customer_requests (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('billing', 'account', 'technical', 'general')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
    summary TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    notification_status TEXT NOT NULL CHECK (
        notification_status IN ('not_required', 'pending', 'sent', 'failed')
    ),
    notification_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

INSERT_REQUEST = """
INSERT INTO customer_requests (
    customer_id, customer_name, customer_email, message,
    category, priority, summary, suggested_action,
    notification_status, notification_error
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING id
"""


class DatabaseError(Exception):
    """The database operation did not complete successfully."""


def initialize_database() -> None:
    """Create the initial table explicitly, never during a webhook request."""
    database_url = get_database_url()
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            connection.execute(CREATE_TABLE)
    except psycopg.Error as exc:
        raise DatabaseError("Could not initialize the database.") from exc


def save_request(
    request: CustomerRequest,
    result: TriageResult,
    notification_status: NotificationStatus,
) -> int:
    """Insert one row and return its ID only after the transaction commits."""
    database_url = get_database_url()
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            cursor = connection.execute(INSERT_REQUEST, (
                request.customer_id, request.customer_name, str(request.customer_email),
                request.message, result.category, result.priority, result.summary,
                result.suggested_action, notification_status, None,
            ))
            row = cursor.fetchone()
            if row is None:
                raise DatabaseError("The insert returned no request ID.")
            request_id = row[0]
        # Exiting the context commits; failures above roll back and close it.
        return request_id
    except psycopg.Error as exc:
        raise DatabaseError("Could not save the request.") from exc


def update_notification_status(
    request_id: int, status: NotificationStatus, error: str | None
) -> None:
    """Commit the notification outcome separately from the original insert."""
    if status not in ("sent", "failed"):
        raise ValueError("Notification outcome must be sent or failed.")
    if status == "sent":
        error = None
    elif not error or not error.strip():
        raise ValueError("Failed notifications require an error reason.")
    database_url = get_database_url()
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            cursor = connection.execute(
                "UPDATE customer_requests SET notification_status = %s, notification_error = %s "
                "WHERE id = %s AND notification_status = 'pending'",
                (status, error, request_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("Pending request was not found for notification update.")
    except psycopg.Error as exc:
        raise DatabaseError("Could not record notification outcome.") from exc


if __name__ == "__main__":
    try:
        initialize_database()
    except (ConfigurationError, DatabaseError):
        raise SystemExit("Database initialization failed. Check configuration and PostgreSQL access.")
    print("Database table is ready.")
