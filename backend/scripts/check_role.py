# import os, psycopg

# with psycopg.connect(os.environ["DATABASE_URL_POOLED"]) as c:
#     print("users:", c.execute("select count(*) from accounts_user").fetchone()[0])
#     try:
#         c.execute("update audit_auditlog set summary = summary where false")
#         print("PROBLEM: the audit log can be updated")
#     except psycopg.errors.InsufficientPrivilege:
#         print("OK: audit log updates are denied")



import os
import psycopg

with psycopg.connect(os.environ["DATABASE_URL_POOLED"]) as c:
    print("Connected role:", c.execute("SELECT current_user").fetchone()[0])

    result = c.execute("""
        SELECT COUNT(*)
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tableowner = current_user
    """).fetchone()[0]

    print("Tables owned by this role:", result)
