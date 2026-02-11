	#!/bin/bash

# Configuration
APP_USER="silkc_user"
APP_DIR="/home/SilkC"
SCREEN_NAME="flask_api"
# Assuming standard hidden .venv folder. If this path is wrong, the script dies.
VENV="$APP_DIR/.venv/bin/activate" 
PORT=1236

# Command to run Gunicorn
CMD="gunicorn -c $APP_DIR/gunicorn_config.py main:app"

# Helper to check if the screen session exists for the specific user
check_status() {
    if sudo -u $APP_USER screen -list | grep -q "$SCREEN_NAME"; then
        return 0 # Running
    else
        return 1 # Not running
    fi
}

case "$1" in
    start)
        if check_status; then
            echo "❌ API is already running!"
        else
			chown -R $APP_USER:$APP_USER $APP_DIR
            echo "🚀 Starting API as user '$APP_USER'..."
            # Start the screen detached
            sudo -u $APP_USER bash -c "source $VENV && screen -dmS $SCREEN_NAME $CMD"
            
            # Wait 2 seconds and verify it didn't crash immediately
            sleep 2
            if check_status; then
                echo "✅ API started successfully on port $PORT."
            else
                echo "⚠️ API failed to start. Check logs via 'console' command."
            fi
        fi
        ;;
	stop)
        echo "🛑 Stopping API..."

        # 1. Attempt Graceful Shutdown of Gunicorn
        # We find the Master PID belonging to the APP_USER
        MASTER_PID=$(pgrep -u $APP_USER -o -f 'gunicorn.*main:app')

        if [ -n "$MASTER_PID" ]; then
            echo "🛑 Sending SIGTERM to master (PID: $MASTER_PID)..."
            # We use 'kill' directly (as root) instead of 'sudo -u ... kill'
            kill -TERM $MASTER_PID 2>/dev/null
        else
            echo "ℹ️ Gunicorn master not found, checking for stragglers..."
        fi

        echo -n "⏳ Waiting for workers to finish requests"

        # Wait loop
        for i in {1..90}; do
			if [ $i -eq 6 ]; then
				pkill -TERM -u $APP_USER -f 'gunicorn.*main:app'
			fi
			
			if [ $i -eq 13 ]; then
				echo -e "\n⚠️ Workers refusing to quit. Sending SIGQUIT (Immediate)..."
				pkill -QUIT -u $APP_USER -f 'gunicorn.*main:app'
			fi	
			
            if pgrep -u $APP_USER -f 'gunicorn.*main:app' > /dev/null; then
                echo -n "."
                sleep 1
            else
                echo ""
                echo "✅ Gunicorn stopped gracefully."
                break
            fi
        done

        # 2. Force Kill if still alive (Nuclear Option)
        # We check if processes exist and force kill as ROOT
        if pgrep -u $APP_USER -f 'gunicorn.*main:app' > /dev/null; then
            echo ""
            echo "⚠️ Workers still alive. Force killing (SIGKILL)..."
            pkill -9 -u $APP_USER -f 'gunicorn.*main:app'
        fi

        # 3. Kill the Screen Session
        # This ensures the shell wrapper is also gone
        if sudo -u $APP_USER screen -list | grep -q "$SCREEN_NAME"; then
            echo "🧹 Cleaning up Screen session..."
            sudo -u $APP_USER screen -X -S $SCREEN_NAME quit 2>/dev/null
            # Fallback if 'quit' fails
            if sudo -u $APP_USER screen -list | grep -q "$SCREEN_NAME"; then
                 pkill -9 -u $APP_USER -f "SCREEN.*$SCREEN_NAME"
            fi
        fi
        
        echo "✅ API stopped and screen session terminated."
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
        
    status)
        if check_status; then
            echo "✅ Status: ONLINE (Screen '$SCREEN_NAME' is active)"
            # Show the actual process ID
            pgrep -u $APP_USER -a -f gunicorn | head -n 1
        else
            echo "⚪ Status: OFFLINE"
        fi
        ;;

    console)
        # This is the magic command to attach to another user's screen
        echo "🔌 Attaching to console... (Press Ctrl+A, then D to detach)"
        sudo -u $APP_USER env SCREENDIR=/run/screen/S-$APP_USER screen -r $SCREEN_NAME
		;;
        
    *)
        echo "Usage: $0 {start|stop|restart|status|console}"
        exit 1
esac