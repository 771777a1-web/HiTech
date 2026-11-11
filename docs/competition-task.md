# Competition Task — Case 1: Autonomous Forest Fire Monitoring

**Skill area:** Flying Robotics
**Initiator / partner:** Autonomous Nonprofit Organization "University 2035"

## Problem

Stopping large forest fires early requires constant monitoring of remote, hard-to-reach areas.
Current approaches take a lot of time and people, and visual inspection can miss hidden
ignition sources at an early stage.

## What competitors build

A UAV hardware/software system with a thermal imaging camera and a neural network that
automatically recognises target objects (e.g. a campfire or a vehicle).

**Key technologies:** computer vision, neural-network object detection (YOLO), thermal image
processing, autonomous navigation, onboard computing (NPU).

**Demonstration:** the UAV flies a predefined route autonomously, processes thermal imagery in
real time, and reliably detects a simulated flame (campfire) at the championship venue.

## Required functionality

| ID | Requirement |
|---|---|
| R1 | Autonomous flight along a predefined route |
| R2 | Onboard thermal camera, thermograms acquired in real time |
| R3 | Neural-network detection of a simulated flame (campfire) in thermal images, **mAP@0.5 ≥ 85%** during the scored flight |
| R4 | Detection of at least one additional object chosen by the team |
| R5 | Onboard video-stream processing on NPU/GPU at **≥ 10 FPS for > 90%** of operating time |
| R6 | Coordinates of each detected object with **error ≤ 0.5 m**, transmitted to a web app, web interface or terminal |
| R7 | Real-time display of detected objects on a map (object type + detection timestamp) |
| R8 | Logging of all events: timestamp, coordinates, object type, model confidence |
| R9 | At least one successful flame detection per flight during the demonstration |
| R10 | Autonomous return on operator command |

Source: `Flying_Robotics_Competition_Tasks_EN.docx`.
