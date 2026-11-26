#!/bin/bash

PRE_DIR='../preprocessor/_preprocessor/'
POST_DIR='../../data/'
TOOL_NAME='captureX'
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

status () {
    echo 'Status:'
    pid=$(ps -aux | grep -F "$SCRIPTPATH" | grep "python3" | grep -v "grep" | awk '{print $2}' | head -n 1)
    if [ -n "$pid" ]
    then
         echo "  Process: $pid"
         echo "    $(ps -aux | grep -F "$SCRIPTPATH" | grep "python3" | grep -v "grep" | awk '{ s = ""; for (i =11; i <= NF; i++) s = s $i " "; print s }')"
         echo ""
    else
        echo "  Not running"
        exit 1
    fi
}

start () {
    echo 'Starting' 
    if [ -z $2 ]; then
        nohup "$PYTHON_BIN" "$SCRIPTPATH/main.py" "$PRE_DIR" "$POST_DIR" "$TOOL_NAME" >> "$SCRIPTPATH/logs/log_post.out" 2>&1 &
    else
        # Start with web api enabled: ./run start 7998
        nohup "$PYTHON_BIN" "$SCRIPTPATH/main.py" "$PRE_DIR" "$POST_DIR" "$TOOL_NAME" "$2" >> "$SCRIPTPATH/logs/log_post.out" 2>&1 &
    fi
}

if [ -d "../../.venv" ]; then
    PYTHON_BIN="../../.venv/bin/python3"
elif [ -d "../.venv" ]; then
    PYTHON_BIN="../.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi
docker () {
    echo 'Starting'
    if [ $# -eq 2 ]
    then
        echo ' Using PORT:' $2
        exec "$PYTHON_BIN" "$SCRIPTPATH/main.py" "$PRE_DIR" "$POST_DIR" "$TOOL_NAME" "$2" >> "$SCRIPTPATH/logs/log_post.out" 2>&1
    else
        echo ' ERROR! Missing PORT configuration.'
        echo ' Please set the port argument'
    fi
}

stop () {
   pids=$(ps -aux | grep -F "$SCRIPTPATH" | grep "python3" | grep -v "grep" | awk '{print $2}')
   if [ -n "$pids" ]; then
       echo "  Process(es): $pids"
       kill -9 $pids
   else
       echo "  Not running"
   fi
}

help () {
   echo 'Usage: '
   echo '  run.sh status'
   echo '  run.sh start'
   echo '  run.sh stop'
}

case $1 in
    status) status ;;
    start) start $# $2 ;;
    docker) docker $# $2 ;;
    stop) stop ;;
    isrunning) status ;;
    *) help ;;
esac
