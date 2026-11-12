#!/usr/bin/env bash
# Airael: start / stop all our services on the drone with one command.
#
#   ~/airael/airael.sh start              page server :8020, thermal JPEG compressor, dataset server
#   ~/airael/airael.sh start --detector   the same + fire detector + geolocation (stops the Skyris rknn_face demo)
#   ~/airael/airael.sh stop               stop everything this script started
#   ~/airael/airael.sh restart [--detector]
#   ~/airael/airael.sh status             what is running, ports and topics
#   ~/airael/airael.sh logs [name]        last lines of the logs (gs, thermal, dataset, detector, geoloc)
#   ~/airael/airael.sh install [--detector]   start at every boot (systemd unit airael.service)
#   ~/airael/airael.sh uninstall          remove the boot unit
#
# The Skyris stack (technic.service: ROS master, rosbridge, cameras) must be running; start waits for it.
# Copies you started by hand are replaced (same ROS node names; the page server is taken over).
# Nothing of Skyris is changed. Settings below can be overridden with environment variables.
# Defaults = the deployed RGB model on the downward camera. Thermal model instead:
#   MODEL=~/airael/models/fire-rk3588.rknn CLASSES='[bonfire, tree]' DET_INPUT=/second_camera/second_camera/image_raw ~/airael/airael.sh start --detector

GS_DIR="${GS_DIR:-$HOME/ground_station}"
GS_PORT="${GS_PORT:-8020}"
DATASET_PY="${DATASET_PY:-$HOME/airael/dataset_server.py}"
MODEL="${MODEL:-$HOME/airael/models/fire-rgb-rk3588.rknn}"
CLASSES="${CLASSES:-[campfire, tree]}"
SIZE="${SIZE:-320}"
THERMAL_IN="${THERMAL_IN:-/second_camera/second_camera/image_raw}"
DET_INPUT="${DET_INPUT:-/main_camera/image_raw}"   # detector camera; thermal model: DET_INPUT=$THERMAL_IN
BASE="$HOME/airael"
RUN="$BASE/run"
LOGS="$BASE/logs"
NAMES="gs thermal dataset detector geoloc"
GEO_PY="${GEO_PY:-$HOME/airael/fire_geoloc.py}"
GEO_HFOV="${GEO_HFOV:-0}"   # thermal only: horizontal field of view in degrees if its camera_info is empty

mkdir -p "$RUN" "$LOGS"

ros_env() {
  # shellcheck disable=SC1091
  [ -f /opt/ros/noetic/setup.bash ] && source /opt/ros/noetic/setup.bash
  for ws in "$HOME/technic_ws/devel/setup.bash" "$HOME/catkin_ws/devel/setup.bash"; do
    # shellcheck disable=SC1090
    if [ -f "$ws" ]; then source "$ws"; fi
  done
  export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
}

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

pid_of()  { [ -f "$RUN/$1.pid" ] && cat "$RUN/$1.pid" 2>/dev/null; }
alive()   { local p; p=$(pid_of "$1"); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

# launch <name> <command...>: own process group, output to logs/<name>.log
launch() {
  local name="$1"; shift
  if alive "$name"; then ok "$name already running (pid $(pid_of "$name"))"; return 0; fi
  {
    printf '\n===== %s  start: %s\n' "$(date '+%F %T')" "$*"
  } >>"$LOGS/$name.log"
  setsid nohup "$@" >>"$LOGS/$name.log" 2>&1 < /dev/null &
  echo $! >"$RUN/$name.pid"
  sleep 1
  if alive "$name"; then ok "$name started (pid $(pid_of "$name"), log $LOGS/$name.log)"
  else bad "$name exited at once. Last log lines:"; tail -n 8 "$LOGS/$name.log" | sed 's/^/      /'; return 1; fi
}

stop_one() {
  local name="$1" p
  p=$(pid_of "$name")
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    # SIGTERM to the whole process group: roslaunch and rospy shut down cleanly on it
    # (SIGINT would be ignored: programs started in the background by a script inherit SIGINT as ignored)
    kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$p" 2>/dev/null && { kill -KILL -- "-$p" 2>/dev/null || kill -KILL "$p" 2>/dev/null; }
    ok "$name stopped"
  fi
  rm -f "$RUN/$name.pid"
}

wait_for_ros() {
  say "Waiting for the Skyris stack (ROS master + rosbridge) …"
  for i in $(seq 1 90); do
    if rostopic list >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':9090 '; then
      ok "ROS master and rosbridge are up"; return 0
    fi
    [ "$i" -eq 1 ] && say "  (technic.service may still be starting; up to 90 s)"
    sleep 1
  done
  bad "ROS master or rosbridge (:9090) not up after 90 s. Check: systemctl status technic"
  return 1
}

port_owner() { ss -ltnp 2>/dev/null | grep ":$1 " | sed -E 's/.*users:\(\("([^"]+)",pid=([0-9]+).*/\1 pid \2/'; }

start_all() {
  local detector="$1"
  ros_env
  say "Starting Airael services ($(date '+%T'))"
  wait_for_ros || return 1

  # 1. page server
  if [ ! -f "$GS_DIR/index.html" ]; then bad "no $GS_DIR/index.html"
  elif alive gs; then ok "gs already running (pid $(pid_of gs))"
  else
    if ss -ltn 2>/dev/null | grep -q ":$GS_PORT " && pgrep -f "http.server $GS_PORT" >/dev/null; then
      pkill -f "http.server $GS_PORT"; sleep 1; ok "stopped a hand-started page server on :$GS_PORT (taking over)"
    fi
    if ss -ltn 2>/dev/null | grep -q ":$GS_PORT "; then
      warn "port $GS_PORT is used by another program: $(port_owner "$GS_PORT"). Free it and run start again."
    else
      launch gs python3 -m http.server "$GS_PORT" --bind 0.0.0.0 --directory "$GS_DIR"
    fi
  fi

  # 2. thermal JPEG for the dashboard
  launch thermal rosrun image_transport republish raw "in:=$THERMAL_IN" compressed out:=/airael/thermal __name:=airael_thermal_compress

  # 3. dataset server
  if [ -f "$DATASET_PY" ]; then launch dataset python3 "$DATASET_PY"
  else bad "no $DATASET_PY (copy dataset_server.py there)"; fi

  # 4. detector (optional)
  if [ "$detector" = 1 ]; then
    if [ ! -f "$MODEL" ]; then bad "no model at $MODEL (set MODEL=/path/to/model.rknn)"
    else
      rosnode kill /rknn_face >/dev/null 2>&1 && ok "stopped Skyris demo /rknn_face (frees the NPU)"
      launch detector roslaunch yolo_face fire_detector.launch "model:=$MODEL" "size:=$SIZE" "classes:=$CLASSES" "input:=$DET_INPUT"
      # 5. geolocation: detections -> positions on the ArUco map (/fire/events)
      if [ -f "$GEO_PY" ]; then
        local ci="${DET_INPUT%/*}/camera_info"   # /main_camera/image_raw -> /main_camera/camera_info
        launch geoloc python3 "$GEO_PY" "_camera_info:=$ci" "_hfov_deg:=$GEO_HFOV"
      else bad "no $GEO_PY: geolocation not started (copy fire_geoloc.py there)"; fi
    fi
  fi
  echo
  status_all
}

stop_all() {
  say "Stopping Airael services"
  for n in geoloc detector dataset thermal gs; do stop_one "$n"; done
  say "(the Skyris stack keeps running; its rknn_face demo comes back at the next technic restart)"
}

status_all() {
  ros_env
  local host; host=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(192\.168\.50|10\.42\.0)\.' | head -1)
  say "Status ($(date '+%T'))"
  for n in $NAMES; do
    if alive "$n"; then ok "$(printf '%-9s' "$n") running, pid $(pid_of "$n")"
    else say "  - $(printf '%-9s' "$n") not running"; fi
  done
  ss -ltn 2>/dev/null | grep -q ":$GS_PORT " && ok "page:     http://${host:-192.168.50.2}:$GS_PORT/" || bad "nothing listens on :$GS_PORT"
  ss -ltn 2>/dev/null | grep -q ':9090 ' && ok "rosbridge :9090" || bad "rosbridge :9090 not listening (Skyris technic.service)"
  if rostopic list >/dev/null 2>&1; then
    local topics; topics=$(rostopic list 2>/dev/null)
    grep -qx '/airael/thermal/compressed' <<<"$topics" && ok "topic /airael/thermal/compressed" || warn "no /airael/thermal/compressed"
    grep -qx '/airael/dataset/status' <<<"$topics" && ok "topic /airael/dataset/status" || warn "no /airael/dataset/status"
    grep -qx '/fire/detections' <<<"$topics" && ok "topic /fire/detections" || say "  - no /fire/detections (detector off)"
    grep -qx '/fire/events' <<<"$topics" && ok "topic /fire/events (geolocation)" || say "  - no /fire/events (geolocation off)"
    rosnode list 2>/dev/null | grep -q '^/rknn_face$' && say "  - Skyris demo /rknn_face is running (uses the NPU)"
  else
    bad "ROS master not reachable"
  fi
}

logs_cmd() {
  local names="${1:-$NAMES}"
  for n in $names; do
    [ -f "$LOGS/$n.log" ] || continue
    printf '\n===== %s (%s)\n' "$n" "$LOGS/$n.log"; tail -n 15 "$LOGS/$n.log"
  done
}

install_unit() {
  local detector="$1" self; self=$(readlink -f "$0")
  local args="start"; [ "$detector" = 1 ] && args="start --detector"
  sudo tee /etc/systemd/system/airael.service >/dev/null <<EOF
[Unit]
Description=Airael services (page server, thermal JPEG, dataset server$( [ "$detector" = 1 ] && echo ", detector"))
After=technic.service network-online.target
Wants=technic.service

[Service]
Type=oneshot
User=$USER
Environment=HOME=$HOME
ExecStart=$self $args
ExecStop=$self stop
RemainAfterExit=yes
TimeoutStartSec=150

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload && sudo systemctl enable airael.service >/dev/null 2>&1 && ok "airael.service installed: '$self $args' runs at every boot"
  say "  Start it now with: sudo systemctl start airael   (or keep using $self start)"
}

case "${1:-}" in
  start)     start_all "$([ "${2:-}" = --detector ] && echo 1 || echo 0)" ;;
  stop)      stop_all ;;
  restart)   stop_all; echo; start_all "$([ "${2:-}" = --detector ] && echo 1 || echo 0)" ;;
  status)    status_all ;;
  logs)      logs_cmd "${2:-}" ;;
  install)   install_unit "$([ "${2:-}" = --detector ] && echo 1 || echo 0)" ;;
  uninstall) sudo systemctl disable --now airael.service 2>/dev/null; sudo rm -f /etc/systemd/system/airael.service; sudo systemctl daemon-reload; ok "airael.service removed" ;;
  *) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
