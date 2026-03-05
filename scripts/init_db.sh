#!/bin/bash
set -e
echo "Initializing DB schema..."
psql "$PG_DSN" -f app/schema/create_tables.sql
echo "Done."
