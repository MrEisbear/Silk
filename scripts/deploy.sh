#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/home/SilkC"
BRANCH="main"
START_SCRIPT="$APP_DIR/start.sh"

die() {
    echo "Deploy failed: $*" >&2
    exit 1
}

for command in git date; do
    command -v "$command" >/dev/null 2>&1 || die "required command '$command' is unavailable"
done

[[ -d "$APP_DIR/.git" ]] || die "Git repository not found at $APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]] || die "virtual environment Python is missing"
[[ -x "$START_SCRIPT" ]] || die "start script is not executable: $START_SCRIPT"

current_branch="$(git -C "$APP_DIR" branch --show-current)"
[[ "$current_branch" == "$BRANCH" ]] ||
    die "expected branch '$BRANCH', found '$current_branch'"
[[ -z "$(git -C "$APP_DIR" status --porcelain)" ]] ||
    die "working tree is not clean; commit or otherwise preserve local changes before deploying"

git -C "$APP_DIR" fetch origin "$BRANCH"
git -C "$APP_DIR" merge-base --is-ancestor HEAD "origin/$BRANCH" ||
    die "origin/$BRANCH is not a fast-forward of the deployed commit"

previous_commit="$(git -C "$APP_DIR" rev-parse HEAD)"
rollback_tag="rollback-$(date -u +%Y%m%d_%H%M%S)"
if git -C "$APP_DIR" show-ref --verify --quiet "refs/tags/$rollback_tag"; then
    die "rollback tag already exists: $rollback_tag"
fi
git -C "$APP_DIR" tag "$rollback_tag" "$previous_commit"
git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"

echo "Running the idempotent auth database migration..."
"$APP_DIR/.venv/bin/python" - "$APP_DIR" "$MIGRATION" <<'PY'
import os
import re
import sys

from dotenv import load_dotenv
import mysql.connector

app_dir, migration_path = sys.argv[1:3]
load_dotenv(os.path.join(app_dir, ".env"))

required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
missing = [name for name in required if not os.getenv(name)]
if missing:
    raise RuntimeError("Missing database settings: " + ", ".join(missing))

connection = mysql.connector.connect(
    host=os.environ["DB_HOST"],
    port=int(os.getenv("DB_PORT") or "3306"),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
)
try:
    with open(migration_path, encoding="utf-8") as migration_file:
        statements = [part.strip() for part in re.split(r";\s*", migration_file.read())]
    with connection.cursor() as cursor:
        for statement in statements:
            if statement:
                cursor.execute(statement)
    connection.commit()
finally:
    connection.close()
PY

if "$START_SCRIPT" status >/dev/null 2>&1; then
    "$START_SCRIPT" reload
else
    "$START_SCRIPT" start
fi

echo "Deployment complete."
echo "Rollback tag: $rollback_tag"
echo "To roll back code: git -C $APP_DIR switch --detach $rollback_tag"
echo "Then restart the API with: $START_SCRIPT restart"
echo "The database schema is not rolled back automatically."
