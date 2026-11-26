#!/bin/bash

PRE_DIR='./_preprocessor/'
POST_DIR='../../data/'
TOOL_NAME='captureX'
BASEDIR=$(dirname "$0")
SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

status () {
    echo 'Status:'
    pid=$(ps -aux | grep -F "$SCRIPTPATH" | grep "node" | grep -v "grep" | awk '{print $2}')
    if [ -n "$pid" ]
    then
         echo "  Process: $pid"
         echo "    $(ps -aux | grep -F "$SCRIPTPATH" | grep "node" | grep -v "grep" | awk '{ s = ""; for (i =11; i <= NF; i++) s = s $i " "; print s }')"
    else
        echo "  Not running"
        exit 1
    fi
}

start () {
    echo 'Starting'
    if [ $# -eq 2 ]
    then
        echo ' Using PORT:' $2
        nohup node "$SCRIPTPATH/server.js" $2 $PRE_DIR $POST_DIR $TOOL_NAME >> "$SCRIPTPATH/log_pre.out" 2>&1 &
    else
        echo ' ERROR! Missing PORT configuration.'
        echo ' Please set the port argument'
        help
        exit 1
    fi
}

docker () {
    echo 'Starting'
    if [ $# -eq 2 ]
    then
        echo ' Using PORT:' $2
        exec node "$SCRIPTPATH/server.js" $2 $PRE_DIR $POST_DIR $TOOL_NAME >> "$SCRIPTPATH/log_pre.out" 2>&1
    else
        echo ' ERROR! Missing PORT configuration.'
        echo ' Please set the port argument'
    fi
}

stop () {
   pid=$(ps -aux | grep -F "$SCRIPTPATH" | grep "node" | grep -v "grep" | awk '{print $2}')
   if [ -n "$pid" ]; then
       echo "  Process: $pid"
       kill -9 $pid
   else
       echo "  Not running"
   fi
}

help () {
   echo 'Usage: '
   echo '  run.sh status'
   echo '  run.sh start <PORT>'
   echo '  run.sh stop'
   echo ''
   echo '  Test env: ./run.sh start 7999'
   echo '  Prod env: ./run.sh start 8081'
   echo ''
}

case $1 in
    status) status ;;
    start) start $@ ;;
    docker) docker $@ ;;
    stop) stop ;;
    *) help ;;
esac
