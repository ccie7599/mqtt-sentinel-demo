#!/usr/bin/env python3
"""
Populate the MQTT auth database with test users for load testing.

This script inserts users into the mqtt_clients table in batches.
Users are created without passwords (client_id only auth).

Usage:
    python populate_users.py --host <db_host> --user <db_user> --password <db_pass> --count 5000

    Or via environment variables:
    DB_HOST=... DB_USER=... DB_PASSWORD=... python populate_users.py --count 5000
"""

import argparse
import os
import sys
import time

try:
    import mysql.connector
except ImportError:
    print("Error: mysql-connector-python required. Install with: pip install mysql-connector-python")
    sys.exit(1)


def create_users(cursor, start_id: int, count: int, batch_size: int = 1000) -> int:
    """Insert users in batches. Returns number of users created."""
    created = 0

    for batch_start in range(start_id, start_id + count, batch_size):
        batch_end = min(batch_start + batch_size, start_id + count)
        values = []

        for i in range(batch_start, batch_end):
            client_id = f"loadtest-user-{i}"
            # Empty secret_hash means no password required
            values.append(f"('{client_id}', '', 'us-east', NULL, 'Load test user {i}')")

        if values:
            sql = f"""
                INSERT IGNORE INTO mqtt_clients
                (client_id, secret_hash, region, permissions, description)
                VALUES {','.join(values)}
            """
            cursor.execute(sql)
            created += cursor.rowcount
            print(f"  Inserted batch {batch_start}-{batch_end-1} ({cursor.rowcount} new users)")

    return created


def get_user_count(cursor, prefix: str = "loadtest-user-") -> int:
    """Get count of existing loadtest users."""
    cursor.execute(
        "SELECT COUNT(*) FROM mqtt_clients WHERE client_id LIKE %s",
        (f"{prefix}%",)
    )
    return cursor.fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description="Populate MQTT auth database with test users")
    parser.add_argument("--host", default=os.getenv("DB_HOST", "localhost"), help="Database host")
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")), help="Database port")
    parser.add_argument("--user", default=os.getenv("DB_USER", "mqtt_auth"), help="Database user")
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", ""), help="Database password")
    parser.add_argument("--database", default=os.getenv("DB_NAME", "mqtt_auth"), help="Database name")
    parser.add_argument("--count", type=int, default=5000, help="Number of users to create")
    parser.add_argument("--start", type=int, default=1, help="Starting user ID")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    parser.add_argument("--delete", action="store_true", help="Delete existing loadtest users first")

    args = parser.parse_args()

    print("=" * 60)
    print("MQTT Auth Database User Population")
    print("=" * 60)
    print(f"Host: {args.host}:{args.port}")
    print(f"Database: {args.database}")
    print(f"Target users: {args.count} (starting at {args.start})")
    print("=" * 60)

    try:
        conn = mysql.connector.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database
        )
        cursor = conn.cursor()

        # Check existing users
        existing = get_user_count(cursor)
        print(f"Existing loadtest users: {existing}")

        if args.delete and existing > 0:
            print("Deleting existing loadtest users...")
            cursor.execute("DELETE FROM mqtt_clients WHERE client_id LIKE 'loadtest-user-%'")
            conn.commit()
            print(f"  Deleted {cursor.rowcount} users")
            existing = 0

        # Create users
        print(f"\nCreating {args.count} users...")
        start_time = time.time()
        created = create_users(cursor, args.start, args.count, args.batch_size)
        conn.commit()
        elapsed = time.time() - start_time

        # Final count
        total = get_user_count(cursor)

        print("=" * 60)
        print(f"Created: {created} new users")
        print(f"Total loadtest users: {total}")
        print(f"Time: {elapsed:.2f}s ({created/elapsed:.0f} users/sec)")
        print("=" * 60)

        cursor.close()
        conn.close()

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
