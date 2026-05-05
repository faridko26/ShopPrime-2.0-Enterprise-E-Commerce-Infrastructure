"""
COMP640 Group-6
apply_migrations.py — Run V1 → V2 → V3 SQL migrations against Neon.

Run:
    python scripts/apply_migrations.py
"""

import os
import re
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL   = os.getenv("DATABASE_URL")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")


def extract_statements(sql: str) -> list[str]:
    """
    Return executable SQL statements from a file.
    Handles:
      - Single-line (--) comments stripped
      - Dollar-quoted PL/pgSQL bodies ($$...$$) kept intact
      - Splits on semicolons outside dollar-quotes
    """
    # Remove single-line comments
    sql = re.sub(r'--[^\n]*', '', sql)

    statements = []
    buf        = []
    in_dollar  = False
    i          = 0

    while i < len(sql):
        ch = sql[i]

        # Detect start/end of dollar-quoting ($$)
        if sql[i:i+2] == '$$':
            in_dollar = not in_dollar
            buf.append('$$')
            i += 2
            continue

        if ch == ';' and not in_dollar:
            stmt = ''.join(buf).strip()
            if stmt:
                statements.append(stmt + ';')
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    # Trailing statement without semicolon
    remainder = ''.join(buf).strip()
    if remainder:
        statements.append(remainder)

    return statements


def run_migrations():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur  = conn.cursor()

    sql_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "V*.sql")))

    for path in sql_files:
        name = os.path.basename(path)
        print(f"\nApplying {name} ...")
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        stmts = extract_statements(raw)
        for idx, stmt in enumerate(stmts, 1):
            try:
                cur.execute(stmt)
                first_line = stmt.strip().splitlines()[0][:70]
                print(f"  [{idx:02d}] OK  — {first_line}")
            except psycopg2.Error as e:
                print(f"  [{idx:02d}] FAILED\n        SQL : {stmt[:120]}\n        Err : {e}")
                cur.close()
                conn.close()
                raise SystemExit(1)

    cur.close()
    conn.close()
    print("\nAll migrations applied successfully.")


if __name__ == "__main__":
    run_migrations()
