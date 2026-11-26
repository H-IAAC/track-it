#!/usr/bin/env bash
# ==============================================================================
# Track-It Toolkit — Unified Orchestrator
# Starts, stops, and monitors all 5 toolkit services in topological order.
# ==============================================================================

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT_DIR/.pids"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

# Color helpers
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

# Find Python binary (use .venv if present)
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [ -f "$ROOT_DIR/face_masking_studio/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/face_masking_studio/.venv/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

# Function to check if a port is in use
is_port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -tulpn 2>/dev/null | grep -q ":${port} "
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tulpn 2>/dev/null | grep -q ":${port} "
    else
        return 1
    fi
}

# Function to kill a process listening on a specific port
kill_port() {
    local port="$1"
    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    fi
}

# Wait for a URL to respond with HTTP 200/OK
wait_for_url() {
    local url="$1"
    local timeout="${2:-15}"
    local count=0
    while ! curl -s -o /dev/null "$url"; do
        sleep 0.5
        count=$((count + 1))
        if [ "$count" -ge "$((timeout * 2))" ]; then
            return 1
        fi
    done
    return 0
}

# Get local LAN IP (typically 192.168.x.x, 10.x.x.x, or active interface IP; never docker bridges or 127.0.0.1)
get_lan_ip() {
    local ip
    # First priority: explicit 192.168.x.x address on non-docker interfaces
    ip=$(ip -4 addr show scope global 2>/dev/null | grep -v "docker" | grep -v "br-" | grep -o "192\.168\.[0-9]*\.[0-9]*" | head -n 1 || true)
    # Second priority: active default route interface IP
    if [ -z "$ip" ]; then
        ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
    fi
    # Third priority: any global non-docker, non-bridge IP
    if [ -z "$ip" ]; then
        ip=$(ip -4 addr show scope global 2>/dev/null | grep -v "docker" | grep -v "br-" | grep "inet " | awk '{print $2}' | cut -d/ -f1 | head -n 1 || true)
    fi
    echo "${ip:-127.0.0.1}"
}

start_all() {
    echo -e "${BOLD}======================================================${NC}"
    echo -e "${BOLD}Starting Track-It Toolkit Services...${NC}"
    echo -e "${BOLD}======================================================${NC}"

    # 1. Track-It Masking Studio (port 8000) - MUST BE FIRST
    echo -e "\n${BLUE}[1/5] Starting Track-It Masking Studio (Port 8000)...${NC}"
    if is_port_in_use 8000; then
        echo -e "      ${YELLOW}Port 8000 already in use. Assuming Masking Studio is running.${NC}"
    else
        cd "$ROOT_DIR/face_masking_studio/backend"
        nohup "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port 8000 --ws websockets < /dev/null > "$LOG_DIR/face_masking.log" 2>&1 &
        local fmpid=$!
        echo $fmpid > "$PID_DIR/face_masking.pid"
        disown $fmpid 2>/dev/null || true
        
        echo -n "      Waiting for Track-It Masking Studio to become ready..."
        if wait_for_url "http://127.0.0.1:8000/api/videos" 15; then
            echo -e " ${GREEN}Ready!${NC}"
        else
            echo -e " ${YELLOW}Started (continuing)...${NC}"
        fi
    fi

    # 2. Track-It Server Preprocessor (port 8080)
    echo -e "\n${BLUE}[2/5] Starting Track-It Server Preprocessor (Port 8080)...${NC}"
    cd "$ROOT_DIR/server-processing/preprocessor"
    if is_port_in_use 8080; then
        echo -e "      ${YELLOW}Port 8080 already in use. Assuming Preprocessor is running.${NC}"
    else
        ./run.sh start 8080
    fi

    # 3. Track-It Server Postprocessor (port 7998)
    echo -e "\n${BLUE}[3/5] Starting Track-It Server Postprocessor (Port 7998)...${NC}"
    cd "$ROOT_DIR/server-processing/postprocessor"
    if is_port_in_use 7998; then
        echo -e "      ${YELLOW}Port 7998 already in use. Assuming Postprocessor is running.${NC}"
    else
        ./run.sh start 7998
    fi

    # 4. Track-It Labeler (port 8050)
    echo -e "\n${BLUE}[4/5] Starting Track-It Labeler (Port 8050)...${NC}"
    if is_port_in_use 8050; then
        echo -e "      ${YELLOW}Port 8050 already in use. Assuming Labeler is running.${NC}"
    else
        cd "$ROOT_DIR/annotation_interface"
        nohup "$PYTHON_BIN" main.py < /dev/null > "$LOG_DIR/annotation.log" 2>&1 &
        local annpid=$!
        echo $annpid > "$PID_DIR/annotation.pid"
        disown $annpid 2>/dev/null || true
        echo -n "      Waiting for Track-It Labeler to become ready..."
        if wait_for_url "http://127.0.0.1:8050/" 15; then
            echo -e " ${GREEN}Ready!${NC}"
        else
            echo -e " ${YELLOW}Started (continuing)...${NC}"
        fi
    fi

    # 5. Track-It Viewer (port 8052)
    echo -e "\n${BLUE}[5/5] Starting Track-It Viewer (Port 8052)...${NC}"
    if is_port_in_use 8052; then
        echo -e "      ${YELLOW}Port 8052 already in use. Assuming Viewer is running.${NC}"
    else
        cd "$ROOT_DIR/viewer_interface"
        nohup "$PYTHON_BIN" visualize_dataset.py < /dev/null > "$LOG_DIR/viewer.log" 2>&1 &
        local viewpid=$!
        echo $viewpid > "$PID_DIR/viewer.pid"
        disown $viewpid 2>/dev/null || true
        
        echo -n "      Waiting for Track-It Viewer to become ready..."
        if wait_for_url "http://127.0.0.1:8052/" 15; then
            echo -e " ${GREEN}Ready!${NC}"
        else
            echo -e " ${YELLOW}Started (continuing)...${NC}"
        fi
    fi

    cd "$ROOT_DIR"
    show_status
}

stop_all() {
    echo -e "${BOLD}Stopping all Track-It Toolkit services...${NC}"

    # 1. Stop Server Preprocessor and Postprocessor via their run scripts
    if [ -f "$ROOT_DIR/server-processing/preprocessor/run.sh" ]; then
        cd "$ROOT_DIR/server-processing/preprocessor" && ./run.sh stop >/dev/null 2>&1 || true
    fi
    if [ -f "$ROOT_DIR/server-processing/postprocessor/run.sh" ]; then
        cd "$ROOT_DIR/server-processing/postprocessor" && ./run.sh stop >/dev/null 2>&1 || true
    fi

    # 2. Stop tracked background processes
    for pidfile in "$PID_DIR"/*.pid; do
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile" 2>/dev/null || true)
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                sleep 0.2
                kill -9 "$pid" 2>/dev/null || true
            fi
            rm -f "$pidfile"
        fi
    done

    # 3. Clean up any remaining processes on the 5 target ports
    for p in 8000 8080 7998 8050 8052; do
        kill_port "$p"
    done

    echo -e "${GREEN}All services stopped cleanly.${NC}"
}

show_status() {
    local lan_ip
    lan_ip=$(get_lan_ip)

    echo ""
    echo -e "${BOLD}========================================================================${NC}"
    echo -e "${BOLD}                       Track-It Toolkit Status                          ${NC}"
    echo -e "${BOLD}========================================================================${NC}"
    printf "%-26s | %-6s | %-10s | %s\n" "Service" "Port" "Status" "URL / Destination"
    echo "---------------------------+--------+------------+---------------------------------------"

    # Track-It Masking Studio
    if is_port_in_use 8000; then
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "Track-It Masking Studio" "8000" "RUNNING" "http://127.0.0.1:8000"
    else
        printf "%-26s | %-6s | ${RED}%-10s${NC} | %s\n" "Track-It Masking Studio" "8000" "STOPPED" "-"
    fi

    # Track-It Server (Preprocessor)
    if is_port_in_use 8080; then
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "Track-It Server (Pre)" "8080" "RUNNING" "http://127.0.0.1:8080 (PC)"
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "  └─► Phone Server Config" "8080" "MOBILE" "http://${lan_ip}:8080"
    else
        printf "%-26s | %-6s | ${RED}%-10s${NC} | %s\n" "Track-It Server (Pre)" "8080" "STOPPED" "-"
    fi

    # Track-It Server (Postprocessor)
    if is_port_in_use 7998; then
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "Track-It Server (Post)" "7998" "RUNNING" "Watchdog Daemon"
    else
        printf "%-26s | %-6s | ${RED}%-10s${NC} | %s\n" "Track-It Server (Post)" "7998" "STOPPED" "-"
    fi

    # Track-It Labeler
    if is_port_in_use 8050; then
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "Track-It Labeler" "8050" "RUNNING" "http://127.0.0.1:8050"
    else
        printf "%-26s | %-6s | ${RED}%-10s${NC} | %s\n" "Track-It Labeler" "8050" "STOPPED" "-"
    fi

    # Track-It Viewer
    if is_port_in_use 8052; then
        printf "%-26s | %-6s | ${GREEN}%-10s${NC} | %s\n" "Track-It Viewer" "8052" "RUNNING" "http://127.0.0.1:8052"
    else
        printf "%-26s | %-6s | ${RED}%-10s${NC} | %s\n" "Track-It Viewer" "8052" "STOPPED" "-"
    fi
    echo -e "${BOLD}========================================================================${NC}"
    echo -e "Logs directory: ${LOG_DIR}/"
    echo -e "Android phone setup: In app settings, set Server Config to ${BOLD}http://${lan_ip}:8080${NC} (never 127.0.0.1)"
    echo -e "${BOLD}========================================================================${NC}\n"
}

run_foreground() {
    trap stop_all SIGINT SIGTERM EXIT
    start_all
    echo -e "${YELLOW}Running in foreground. Press Ctrl+C to stop all services.${NC}"
    while true; do
        sleep 2
    done
}

show_logs() {
    local target="$1"
    case "$target" in
        face-mask|facemask|mask)
            echo -e "${BLUE}Streaming logs for Face Masking Studio...${NC}"
            tail -n 50 -f "$LOG_DIR/face_masking.log"
            ;;
        server-pre|pre|preprocessor)
            echo -e "${BLUE}Streaming logs for Server Preprocessor...${NC}"
            tail -n 50 -f "$ROOT_DIR/server-processing/preprocessor/log_pre.out"
            ;;
        server-post|post|postprocessor)
            echo -e "${BLUE}Streaming logs for Server Postprocessor...${NC}"
            tail -n 50 -f "$ROOT_DIR/server-processing/postprocessor/logs/log_post.out"
            ;;
        annotation|annotate)
            echo -e "${BLUE}Streaming logs for Annotation Interface...${NC}"
            tail -n 50 -f "$LOG_DIR/annotation.log"
            ;;
        viewer|dataset-viewer)
            echo -e "${BLUE}Streaming logs for Dataset Viewer...${NC}"
            tail -n 50 -f "$LOG_DIR/viewer.log"
            ;;
        all|"")
            echo -e "${BLUE}Streaming logs for all services (use Ctrl+C to exit)...${NC}"
            echo -e "${YELLOW}Tip: filter by service using: $0 logs [viewer|server-pre|server-post|face-mask|annotation]${NC}\n"
            tail -n 20 -f "$LOG_DIR"/*.log "$ROOT_DIR"/server-processing/preprocessor/log_pre.out "$ROOT_DIR"/server-processing/postprocessor/logs/log_post.out 2>/dev/null
            ;;
        *)
            echo -e "${RED}Unknown log target: '$target'${NC}"
            echo -e "Available options: ${BOLD}viewer${NC}, ${BOLD}server-pre${NC}, ${BOLD}server-post${NC}, ${BOLD}face-mask${NC}, ${BOLD}annotation${NC}, ${BOLD}all${NC}"
            exit 1
            ;;
    esac
}

case "${1:-start}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 1
        start_all
        ;;
    status)
        show_status
        ;;
    foreground)
        run_foreground
        ;;
    logs)
        show_logs "$2"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|foreground|logs [service]}"
        echo "  logs options: viewer, server-pre, server-post, face-mask, annotation, all"
        exit 1
        ;;
esac
