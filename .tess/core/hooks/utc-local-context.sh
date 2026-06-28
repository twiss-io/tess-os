#!/usr/bin/env bash
# UserPromptSubmit hook — injects the current UTC and local timestamps into
# context on every turn. Closes the recurring UTC-read-as-local failure class
# (G16 / QW3, audit reform 2026-06-10): Telegram ts="...Z" values are UTC, and
# misreading UTC timestamps as local time can mistime scheduled actions.
# Set TESS_LOCAL_TZ (IANA name, e.g. America/New_York) to your local timezone;
# defaults to UTC.
# WARN/INFO ONLY — this hook never blocks anything (always exit 0).

local_tz="${TESS_LOCAL_TZ:-UTC}"
utc="$(date -u '+%Y-%m-%d %H:%M:%S')"
local_time="$(TZ="$local_tz" date '+%Y-%m-%d %H:%M:%S')"
offset="$(TZ="$local_tz" date '+%z')"

echo "UTC=${utc}Z / LOCAL=${local_time} (${local_tz}, UTC${offset}). Telegram channel ts=\"...Z\" values are UTC: convert to your local timezone (TESS_LOCAL_TZ=${local_tz}) before any time-of-day reasoning."

exit 0
