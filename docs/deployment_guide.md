# Deployment guide

Written so that someone who did not develop the system can install it. Every command says where it runs:
**laptop** (Linux; tested on Fedora with Python 3.11), **WSL** (Ubuntu under Windows, for GPU training), or
**drone** (Orange Pi 5 Pro on the SKYRIS Technic image, user `orangepi`).

If you only need to fly with an existing model, do sections 1, 4, 5 and 7.

## 1. Get the repository (laptop)

```bash
git clone <repository URL> brics-firewatch
cd brics-firewatch
python3 -m unittest discover -s tests -v      # optional check, needs numpy and pillow (requirements-dev.txt)
```

## 2. Dataset (laptop)

Recording happens on the drone from the ground station's **Dataset** tab (sessions in `~/dataset/<label>_<date>_<time>/`).
Copy the sessions to the laptop:
```bash
rsync -av orangepi@192.168.50.2:/home/orangepi/dataset/ ~/dataset/
```

Label the images, then build a YOLO dataset split **by session** (neighbouring frames are near copies, so a
random split would overstate mAP). Two ways were used:

- **Roboflow (the deployed RGB model).** Upload the RGB frames, draw boxes `campfire` and `tree`, export
  "YOLOv8" without augmentation, then:
  ```bash
  python3 training/yolo_prep.py rfimport --zip "<export.zip or unzipped folder>" --out-images ~/yolo/rgb_img --labels ~/yolo/rgb_labels --classes campfire,tree
  python3 training/yolo_prep.py build --images ~/yolo/rgb_img --labels ~/yolo/rgb_labels --classes campfire,tree --out ~/yolo/ds_rgb
  ```
- **makesense.ai (thermal frames).** Collect, label in the browser, unzip the YOLO labels into `~/yolo/labels`, then build:
  ```bash
  python3 training/yolo_prep.py collect --src ~/dataset --out ~/yolo/to_label --every 2 --max 150
  python3 training/yolo_prep.py build --images ~/yolo/to_label --labels ~/yolo/labels --classes bonfire,tree --out ~/yolo/ds
  ```

Sessions whose name starts with `test_` go to validation; otherwise about 20 % of the sessions of each label.
Check the printed table: every class needs boxes in `val`.

## 3. Train and export to the NPU format

The model must be **YOLOv8** (the detector decodes the single YOLOv8 output `(1, 4+classes, N)`), input 320.

**CPU, Linux laptop** (about 20 s per epoch for 153 training images on an i7-1255U):
```bash
python3.11 -m venv ~/yolo/venv && source ~/yolo/venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-laptop.txt
yolo detect train data=$HOME/yolo/ds_rgb/data.yaml model=yolov8n.pt imgsz=320 epochs=60 patience=20 batch=16 cache=ram \
  hsv_h=0 flipud=0.5 fliplr=0.5 degrees=10 project=$HOME/yolo/runs name=fire_rgb exist_ok=True
yolo detect val model=$HOME/yolo/runs/fire_rgb/weights/best.pt data=$HOME/yolo/ds_rgb/data.yaml imgsz=320
cd $HOME/yolo/runs/fire_rgb/weights && yolo export model=best.pt format=rknn name=rk3588 imgsz=320
```
The export writes `best_rknn_model/best-rk3588.rknn` and reports the output shape `(1, 6, 2100)` for two classes.
`hsv_h=0` keeps colour (the red campfire); for thermal frames also add `hsv_s=0`.
If the export stalls on "attempting AutoUpdate", press Ctrl+C, run `pip install "onnx==1.16.1" "onnxslim>=0.1.82"` and export again.

**NVIDIA GPU under WSL:** zip the dataset folder (`~/yolo/ds_rgb`), then in WSL:
```bash
bash training/train_gpu.sh /mnt/c/Users/<you>/Downloads/ds_rgb.zip
```
It installs PyTorch (CUDA 12.8) and Ultralytics, trains, validates, exports to `.rknn` and packs everything
into `~/yolo/out_fire_rgb.zip` (also copied to the Windows Downloads folder).

## 4. Install on the drone

The drone has no internet; everything is copied from the laptop.

**Laptop:**
```bash
scp -r brics-firewatch orangepi@192.168.50.2:~/
ssh orangepi@192.168.50.2 "mkdir -p ~/airael/models"
scp $HOME/yolo/runs/fire_rgb/weights/best_rknn_model/best-rk3588.rknn orangepi@192.168.50.2:~/airael/models/fire-rgb-rk3588.rknn
```

**Drone:**
```bash
cd ~/brics-firewatch && bash drone/install_drone.sh
```
The installer copies our files to `~/airael/`, the ground station to `~/ground_station/index.html`, and adds
`fire_detector_node.py` and `fire_detector.launch` to the SKYRIS `yolo_face` package (it overwrites no SKYRIS
file). It then checks the model, the NPU runtime (`rknnlite`), OpenCV, ROS and `technic.service`.
`bash drone/install_drone.sh --check` only reports what differs.

Start and check:
```bash
~/airael/airael.sh start --detector
~/airael/airael.sh status
~/airael/airael.sh logs detector     # expect "model outputs: [(1, 6, 2100)]" and "FPS 30.x" lines
```

Other models or cameras need no code change, for example a thermal model:
```bash
MODEL=~/airael/models/fire-rk3588.rknn CLASSES='[bonfire, tree]' DET_INPUT=/second_camera/second_camera/image_raw ~/airael/airael.sh restart --detector
```

## 5. Network (once)

**Ethernet** (used for development): give the drone a permanent address. On the drone (for example from the
SKYRIS web terminal over Wi-Fi):
```bash
sudo nmcli con add type ethernet ifname enP4p65s0 con-name laptop-eth ipv4.method manual ipv4.addresses 192.168.50.2/24
sudo nmcli con up laptop-eth
```
On the laptop, a matching profile (replace `<eth-if>` with the laptop's Ethernet interface from `ip -br link`):
```bash
sudo nmcli con add type ethernet ifname <eth-if> con-name drone-eth ipv4.method manual ipv4.addresses 192.168.50.1/24
sudo nmcli con up drone-eth
ping -c 3 192.168.50.2 && ssh orangepi@192.168.50.2
```

**Wi-Fi:** join the drone's access point; the drone is `10.42.0.1`. The page is then `http://10.42.0.1:8020/`.
(Not yet tested with our software: test before the formal run.)

The drone clock can reset after a reboot; set it from the laptop before flying:
```bash
ssh -t orangepi@192.168.50.2 "sudo date -s @$(date +%s)"
```

## 6. Start at boot (optional, drone)

```bash
~/airael/airael.sh install --detector     # systemd unit airael.service, after technic.service
sudo systemctl start airael
~/airael/airael.sh uninstall              # remove it again
```

## 7. Fixes needed on the SKYRIS image we were given

These were found on our drone (details in the [defect log](module_B/defect_log.md)). Check them on a new drone.

- **D1 thermal camera device and size.** In `~/technic_ws/src/technic/technic/launch/second_camera.launch`
  the thermal camera must be `/dev/camera_second` at 256×192 (it was `/dev/video2` at 640×480).
  Keep a backup (`.bak`). Check: `timeout 6 rostopic hz /second_camera/second_camera/image_raw` shows about 25 Hz.
  This is the one SKYRIS file the team changed.
- **D4 compressed image transport missing** (SKYRIS `*_web_compress` nodes restart in a loop). Install
  `ros-noetic-compressed-image-transport` with `dpkg --ignore-depends=libturbojpeg,libturbojpeg0-dev` and put
  Debian 11's `libturbojpeg.so.0*` in `/usr/local/lib`, then `sudo ldconfig`.
  Check: `timeout 6 rostopic hz /main_camera/image_web/compressed` shows about 30 Hz.
  **Never run `apt --fix-broken install`**: it removes the plugin again.
  Undo: `sudo dpkg -r ros-noetic-compressed-image-transport; sudo rm /usr/local/lib/libturbojpeg.so.0*; sudo ldconfig`.
- **D3 PX4 battery cells:** `rosrun mavros mavparam set BAT1_N_CELLS 6`, and calibrate the voltage divider in
  QGroundControl → Vehicle Setup → Power. Also `COM_DISARM_LAND` above 0 (for example `rosrun mavros mavparam set COM_DISARM_LAND 2`).

## 8. Update or remove

Update: copy the new repository folder and run `bash drone/install_drone.sh` again, then
`~/airael/airael.sh restart --detector`. Remove: `~/airael/airael.sh stop`, `~/airael/airael.sh uninstall`,
delete `~/airael`, `~/ground_station`, and the two files the installer added in the `yolo_face` package
(`scripts/fire_detector_node.py`, `launch/fire_detector.launch`).

## Independent install test (TODO)

Module A asks that someone who did not write the code installs it on a second laptop and records the result.
Fill in after the test: date, tester, environment, result.
