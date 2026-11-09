# CryptoNova 72 — Security Review

Development project `wmirifmgaftassgrfbyl` only. No credential was printed or rotated.

## Exposure audit

| Location | Result |
| --- | --- |
| Git-tracked files | Connection-string examples use placeholders (`YOUR_PASSWORD`, localhost, or one-character fixtures). No non-placeholder development password is in the current tree. |
| Git history (`pooler.supabase.com`) | Two historical matches for the development user were one-character fixtures. No long password was found in tracked history. |
| `.env` and `apps/api/.env.development` | Gitignored and not tracked. |
| Current terminal logs | Matching connection strings are redacted. |
| Local agent transcripts | Non-placeholder connection strings for the development pooler user are present. Treat those local logs as exposed. |

The earlier driver failure that included a connection string was not copied into this report.

## Rotation plan (not executed)

1. Rotate the development database password in the Supabase dashboard for project `wmirifmgaftassgrfbyl`.
2. Update the local gitignored `DATABASE_URL` only. Do not commit it.
3. Restart the development API on `127.0.0.1:8200`.
4. Confirm Alembic `current` still reports `20261108_0011` and that startup logs show a redacted URL.
5. Leave production credentials untouched. None were used.

Services that must receive the new development password: the API engine, Alembic, news/LLM/paper/signal repositories, and any local script that loads `.env`.

## Logging

Startup connection failures already print the exception type only. Configuration errors and Alembic target errors now pass through `redact_connection_strings` before they are printed or re-raised. A unit test checks that an embedded password does not survive that helper.

## Database role

The live session user is `postgres`. It is not a superuser. `rolbypassrls` is true, so row-level security does not constrain this API. Application tables in schema `app` have RLS enabled except `alembic_version`. RLS is not forced. `information_schema.role_table_grants` returned no privileges for `anon`, `authenticated`, or `service_role`.

The Option A least-privilege roles were not created and the runtime URL was not swapped.

## Approval required

Approve rotating the development database password for `wmirifmgaftassgrfbyl` only, then updating the gitignored local URL and restarting the development API.
