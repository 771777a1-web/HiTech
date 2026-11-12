#!/usr/bin/env bash
# Airael: train YOLOv8n on an NVIDIA GPU under WSL (Ubuntu), check mAP, export to rknn, pack the results.
#
# Usage (inside WSL):
#   bash train_gpu.sh /mnt/c/Users/<you>/Downloads/ds_rgb.zip            # dataset zip made on the Fedora laptop
#   bash train_gpu.sh /mnt/c/Users/<you>/Downloads/ds_rgb.zip fire_rgb2   # optional run name
#
# Steps (each is skipped when already done, so re-running is cheap):
#   0 checks: GPU visible in WSL, system packages
#   1 venv ~/yolo/venv_gpu: PyTorch CUDA 12.8 build (needed for RTX 50xx / Blackwell) + Ultralytics
#   2 dataset copied into WSL's own disk (~/yolo), data.yaml path fixed
#   3 train YOLOv8n, imgsz 320, on the GPU
#   4 validate: mAP50 per class (MC2 needs campfire >= 0.85)
#   5 export to rknn (RK3588) in a separate venv ~/yolo/venv_rknn (rknn-toolkit2 2.3.2, CPU torch)
#   6 pack best.pt, best-rk3588.rknn and the plots into one zip, copied to Windows Downloads
set -euo pipefail

ZIP="${1:?usage: bash train_gpu.sh /path/to/ds_rgb.zip [run_name]}"
NAME="${2:-fire_rgb}"
EPOCHS="${EPOCHS:-150}"
PATIENCE="${PATIENCE:-40}"
BATCH="${BATCH:-16}"
IMGSZ="${IMGSZ:-320}"
Y="$HOME/yolo"
GPU_VENV="$Y/venv_gpu"
RKNN_VENV="$Y/venv_rknn"
T0=$(date +%s)

step() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mSTOP: %s\033[0m\n' "$*"; exit 1; }
mkdir -p "$Y"

# ------------------------------------------------------------------ 0 checks
step "0/6 checks"
[ -f "$ZIP" ] || die "dataset zip not found: $ZIP"
command -v nvidia-smi >/dev/null || [ -x /usr/lib/wsl/lib/nvidia-smi ] || \
  die "nvidia-smi not found in WSL. Install/update the NVIDIA driver on WINDOWS (not inside WSL), then run 'wsl --shutdown' in PowerShell and reopen Ubuntu."
export PATH="$PATH:/usr/lib/wsl/lib"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || die "nvidia-smi failed"
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "python3 $PYV"
need=()
for p in python3-venv python3-pip unzip zip libgl1 libglib2.0-0; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
if [ ${#need[@]} -gt 0 ]; then
  echo "installing: ${need[*]}"; sudo apt-get update -qq && sudo apt-get install -y -qq "${need[@]}"
fi

# ------------------------------------------------------------------ 1 GPU venv
step "1/6 PyTorch (CUDA 12.8) + Ultralytics in $GPU_VENV"
if [ ! -x "$GPU_VENV/bin/yolo" ]; then
  python3 -m venv "$GPU_VENV"
  "$GPU_VENV/bin/pip" install -q -U pip
  "$GPU_VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
  "$GPU_VENV/bin/pip" install -q ultralytics
fi
"$GPU_VENV/bin/python" - <<'EOF' || die "PyTorch cannot use the GPU (see above)"
import torch, sys
ok = torch.cuda.is_available()
print('torch', torch.__version__, '| CUDA', torch.version.cuda, '| GPU available:', ok)
if not ok: sys.exit(1)
cap = torch.cuda.get_device_capability(0); arch = 'sm_%d%d' % cap
print('GPU:', torch.cuda.get_device_name(0), arch, '| supported by this torch build:', arch in torch.cuda.get_arch_list())
if arch not in torch.cuda.get_arch_list(): sys.exit(1)
x = torch.randn(2048, 2048, device='cuda'); torch.cuda.synchronize(); print('GPU test OK:', float((x @ x).sum()) == float((x @ x).sum()))
EOF

# ------------------------------------------------------------------ 2 dataset
step "2/6 dataset -> $Y/data_$NAME (WSL disk; /mnt/c is much slower)"
D="$Y/data_$NAME"
rm -rf "$D" && mkdir -p "$D" && unzip -q "$ZIP" -d "$D"
YAML=$(find "$D" -name data.yaml | head -1)
[ -n "$YAML" ] || die "no data.yaml in $ZIP (zip the folder made by: yolo_prep.py build ... --out ~/yolo/ds_rgb)"
DS=$(dirname "$YAML")
sed -i "s#^path:.*#path: $DS#" "$YAML"
grep -q '^path:' "$YAML" || sed -i "1i path: $DS" "$YAML"
echo "data.yaml: $YAML"; cat "$YAML"
for s in train val; do echo "$s: $(ls "$DS/images/$s" 2>/dev/null | wc -l) images"; done

# ------------------------------------------------------------------ 3 train
step "3/6 train YOLOv8n  (imgsz $IMGSZ, batch $BATCH, up to $EPOCHS epochs, patience $PATIENCE)"
cd "$Y"
"$GPU_VENV/bin/yolo" detect train data="$YAML" model=yolov8n.pt imgsz="$IMGSZ" epochs="$EPOCHS" patience="$PATIENCE" \
  batch="$BATCH" device=0 workers=4 cache=ram amp=True hsv_h=0 flipud=0.5 fliplr=0.5 degrees=10 \
  project="$Y/runs" name="$NAME" exist_ok=True plots=True
W="$Y/runs/$NAME/weights"
[ -f "$W/best.pt" ] || die "training produced no best.pt"

# ------------------------------------------------------------------ 4 validate
step "4/6 validate best.pt (MC2: campfire mAP50 >= 0.85)"
"$GPU_VENV/bin/yolo" detect val model="$W/best.pt" data="$YAML" imgsz="$IMGSZ" device=0 \
  project="$Y/runs" name="${NAME}_val" exist_ok=True 2>&1 | tee "$Y/runs/$NAME/val.txt"

# ------------------------------------------------------------------ 5 export rknn
step "5/6 export to rknn (rk3588, toolkit 2.3.2) in $RKNN_VENV"
RKNN_OK=1
case "$PYV" in 3.8|3.9|3.10|3.11|3.12) ;; *) RKNN_OK=0; echo "python $PYV is not supported by rknn-toolkit2 2.3.2: export on a Linux laptop instead (docs/deployment_guide.md, section 3)";; esac
if [ "$RKNN_OK" = 1 ]; then
  if [ ! -x "$RKNN_VENV/bin/yolo" ]; then
    python3 -m venv "$RKNN_VENV"
    "$RKNN_VENV/bin/pip" install -q -U pip
    "$RKNN_VENV/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
    "$RKNN_VENV/bin/pip" install -q ultralytics "rknn-toolkit2==2.3.2" || RKNN_OK=0
  fi
fi
if [ "$RKNN_OK" = 1 ]; then
  (cd "$W" && "$RKNN_VENV/bin/yolo" export model=best.pt format=rknn name=rk3588 imgsz="$IMGSZ") || RKNN_OK=0
fi
RKNN=$(find "$W" -name '*.rknn' 2>/dev/null | head -1 || true)
[ -n "$RKNN" ] && echo "rknn: $RKNN" || echo "rknn export did not work here: copy best.pt to the Fedora laptop and export there"

# ------------------------------------------------------------------ 6 pack
step "6/6 pack results"
OUT="$Y/out_$NAME.zip"; rm -f "$OUT"
R="$Y/runs/$NAME"
( cd "$R" && zip -q -j "$OUT" weights/best.pt results.csv results.png args.yaml val.txt \
    confusion_matrix*.png ./*PR_curve.png ./*F1_curve.png 2>/dev/null || true )
[ -n "$RKNN" ] && zip -q -j "$OUT" "$RKNN"
WIN_DL=""
if command -v cmd.exe >/dev/null 2>&1; then
  WP=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')
  [ -n "$WP" ] && WIN_DL="$(wslpath "$WP")/Downloads"
fi
[ -n "$WIN_DL" ] && [ -d "$WIN_DL" ] && cp "$OUT" "$WIN_DL/" && echo "copied to Windows: $WIN_DL/$(basename "$OUT")"
unzip -l "$OUT" | tail -n +4 | head -n -2
printf '\n\033[1;32mDone in %d min.\033[0m Results: %s\n' $(( ($(date +%s) - T0) / 60 )) "$OUT"
grep -E '^\s+(all|campfire|tree)\s' "$Y/runs/$NAME/val.txt" | sed 's/^/  /' || true
echo "  columns: Class Images Instances Box(P R mAP50 mAP50-95)"
