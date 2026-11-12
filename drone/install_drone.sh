#!/usr/bin/env bash
# Team Brics: install our files on the drone (Orange Pi 5 Pro, SKYRIS Technic image).
# Run ON THE DRONE from the copied repository folder:
#   cd ~/brics-firewatch && bash drone/install_drone.sh            # install / update
#   cd ~/brics-firewatch && bash drone/install_drone.sh --check    # only check, change nothing
#
# What it does (nothing of Skyris is overwritten; our two files are ADDED to the yolo_face package):
#   ~/airael/airael.sh, fire_geoloc.py, dataset_server.py, dataset_capture.py, flight_report.py
#   ~/airael/models/                     (put fire-rgb-rk3588.rknn here; it is not in the repository)
#   ~/ground_station/index.html          (dashboard served on port 8020)
#   <yolo_face>/scripts/fire_detector_node.py and <yolo_face>/launch/fire_detector.launch
# Override locations for a test: AIRAEL_DIR=... GS_DIR=... YOLO_FACE_DIR=... bash drone/install_drone.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
AIRAEL_DIR="${AIRAEL_DIR:-$HOME/airael}"
GS_DIR="${GS_DIR:-$HOME/ground_station}"
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; FAIL=1; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
FAIL=0

if [ -z "${YOLO_FACE_DIR:-}" ]; then
  [ -f /opt/ros/noetic/setup.bash ] && . /opt/ros/noetic/setup.bash
  [ -f "$HOME/technic_ws/devel/setup.bash" ] && . "$HOME/technic_ws/devel/setup.bash"
  YOLO_FACE_DIR="$(rospack find yolo_face 2>/dev/null || true)"
  [ -n "$YOLO_FACE_DIR" ] || YOLO_FACE_DIR="$HOME/technic_ws/src/yolo_face"
fi

echo "Repository : $REPO"
echo "Install to : $AIRAEL_DIR, $GS_DIR, $YOLO_FACE_DIR/{scripts,launch}"

copy() {   # copy <src> <dst> [mode]
  if [ "$CHECK" = 1 ]; then
    if cmp -s "$1" "$2"; then ok "$2 is up to date"; else warn "$2 differs from the repository (run without --check)"; fi
    return
  fi
  mkdir -p "$(dirname "$2")" && cp "$1" "$2" && chmod "${3:-644}" "$2" && ok "$2"
}

[ -d "$YOLO_FACE_DIR" ] || bad "Skyris package yolo_face not found at $YOLO_FACE_DIR (is this the SKYRIS Technic image?)"

copy "$REPO/drone/airael.sh"            "$AIRAEL_DIR/airael.sh" 755
copy "$REPO/drone/fire_geoloc.py"       "$AIRAEL_DIR/fire_geoloc.py" 755
copy "$REPO/drone/dataset_server.py"    "$AIRAEL_DIR/dataset_server.py" 755
copy "$REPO/drone/dataset_capture.py"   "$AIRAEL_DIR/dataset_capture.py" 755
copy "$REPO/drone/flight_report.py"     "$AIRAEL_DIR/flight_report.py" 755
copy "$REPO/ground_station/index.html"  "$GS_DIR/index.html" 644
if [ -d "$YOLO_FACE_DIR" ]; then
  copy "$REPO/drone/fire_detector_node.py" "$YOLO_FACE_DIR/scripts/fire_detector_node.py" 755
  copy "$REPO/drone/fire_detector.launch"  "$YOLO_FACE_DIR/launch/fire_detector.launch" 644
fi
[ "$CHECK" = 1 ] || mkdir -p "$AIRAEL_DIR/models" "$AIRAEL_DIR/flights"

echo "Checks:"
MODEL="$AIRAEL_DIR/models/fire-rgb-rk3588.rknn"
[ -f "$MODEL" ] && ok "model $MODEL" || warn "no model at $MODEL: copy it from the laptop (docs/deployment_guide.md, section 4)"
python3 -c "import rknnlite.api" 2>/dev/null && ok "rknnlite (NPU runtime) importable" || warn "python3 cannot import rknnlite: needed by the detector (rknn-toolkit-lite2 2.3.0 is on the Technic image)"
python3 -c "import cv2, numpy" 2>/dev/null && ok "OpenCV and numpy" || warn "python3 cannot import cv2/numpy"
command -v rosrun >/dev/null 2>&1 && ok "ROS found" || warn "ROS (rosrun) not on PATH: source /opt/ros/noetic/setup.bash"
systemctl is-active --quiet technic 2>/dev/null && ok "technic.service running" || warn "technic.service not running (Skyris stack): sudo systemctl start technic"

[ "$FAIL" = 0 ] && echo "Done. Start with: $AIRAEL_DIR/airael.sh start --detector" || { echo "Finished with errors (see ✗ above)."; exit 1; }
