#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="silkc_user"
APP_DIR="/home/SilkC"
SCREEN_NAME="flask_api"
GUNICORN="$APP_DIR/.venv/bin/gunicorn"
GUNICORN_CONFIG="$APP_DIR/gunicorn_config.py"
PORT=1236

usage() {
    echo "Usage: $0 {start|stop|restart|reload|status|console}"
}

require_runtime() {
    local command
    for command in sudo screen pgrep ps; do
        if ! command -v "$command" >/dev/null 2>&1; then
            echo "Required command not found: $command" >&2
            exit 1
        fi
    done
    if [[ ! -x "$GUNICORN" || ! -f "$GUNICORN_CONFIG" ]]; then
        echo "Gunicorn or its configuration is missing under $APP_DIR." >&2
        exit 1
    fi
}

master_pid() {
    local screen_pid pid process_args
    screen_pid="$(pgrep -u "$APP_USER" -o -f "^SCREEN -dmS ${SCREEN_NAME} " || true)"
    if [[ -n "$screen_pid" ]]; then
        while read -r pid; do
            [[ -n "$pid" ]] || continue
            process_args="$(ps -p "$pid" -o args= || true)"
            if [[ "$process_args" == *"$GUNICORN_CONFIG main:app"* ||
                  "$process_args" == *"gunicorn: master [main:app]"* ]]; then
                printf '%s\n' "$pid"
                return 0
            fi
        done < <(pgrep -P "$screen_pid" || true)
    fi

    return 0
}

screen_exists() {
    sudo -u "$APP_USER" screen -list 2>/dev/null |
        grep -Eq "[0-9]+\\.${SCREEN_NAME}([[:space:]]|$)"
}

stop_screen() {
    if screen_exists; then
        sudo -u "$APP_USER" screen -S "$SCREEN_NAME" -X quit
    fi
}

start_api() {
    if [[ -n "$(master_pid)" ]]; then
        echo "API is already running."
        return 0
    fi

    sudo -u "$APP_USER" screen -dmS "$SCREEN_NAME" \
        bash -c 'cd "$1" && exec "$2" -c "$3" main:app' \
        _ "$APP_DIR" "$GUNICORN" "$GUNICORN_CONFIG"

    for _ in {1..20}; do
        if [[ -n "$(master_pid)" ]]; then
            echo "API started successfully on port $PORT."
            return 0
        fi
        sleep 0.5
    done

    echo "API failed to start; inspect its output with '$0 console'." >&2
    stop_screen || true
    return 1
}

stop_api() {
    local pid
    pid="$(master_pid)"
    if [[ -z "$pid" ]]; then
        stop_screen || true
        echo "API is already stopped."
        return 0
    fi

    echo "Stopping Gunicorn master (PID $pid)..."
    kill -TERM "$pid"
    for _ in {1..30}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            stop_screen || true
            echo "API stopped."
            return 0
        fi
        sleep 1
    done

    echo "Gunicorn did not stop in time; requesting immediate shutdown." >&2
    kill -QUIT "$pid" 2>/dev/null || true
    for _ in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            stop_screen || true
            echo "API stopped."
            return 0
        fi
        sleep 1
    done

    local worker_pid
    while read -r worker_pid; do
        [[ -n "$worker_pid" ]] && kill -KILL "$worker_pid" 2>/dev/null || true
    done < <(pgrep -P "$pid" || true)
    kill -KILL "$pid" 2>/dev/null || true
    stop_screen || true
    echo "API required forced termination." >&2
}

require_runtime

case "${1:-}" in
    start)
        start_api
        ;;
    stop)
        stop_api
        ;;
    restart)
        stop_api
        start_api
        ;;
    reload)
        pid="$(master_pid)"
        if [[ -z "$pid" ]]; then
            echo "API is not running; use '$0 start'." >&2
            exit 1
        fi
        kill -HUP "$pid"
        echo "Gunicorn reload signal sent to master PID $pid."
        ;;
    status)
        pid="$(master_pid)"
        if [[ -n "$pid" ]]; then
            echo "API is online (Gunicorn master PID $pid, port $PORT)."
            ps -p "$pid" -o args=
        else
            echo "API is offline."
            exit 1
        fi
        ;;
    console)
        if ! screen_exists; then
            echo "Screen session '$SCREEN_NAME' is not running." >&2
            exit 1
        fi
        sudo -u "$APP_USER" screen -r "$SCREEN_NAME"
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
