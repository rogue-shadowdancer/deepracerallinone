---
name: deepracer-open-source-navigator
description: Navigate AWS DeepRacer open-source code, documentation, and setup paths. Use when Codex needs to find or explain AWS DeepRacer vehicle-side ROS2/device code, training and simulator code, DeepRacer on AWS deployment code, model export/deployment paths, or sample projects such as Follow the Leader, Mapping, and Offroad.
---

# DeepRacer Open Source Navigator

## Overview

Use this skill to orient work across the AWS DeepRacer open-source ecosystem. It separates vehicle-side ROS2/device code from training, simulator, and cloud-side code, then points Codex to the right repositories and official docs.

For detailed links and repository roles, read `references/source-map.md`.

## Workflow

1. Classify the request:
   - Vehicle runtime, sensors, servos, camera, LiDAR, device console, ROS2 services, or physical car behavior: use `vehicle-code/` and the `aws-deepracer` organization.
   - Training jobs, reward functions, model import/export, simulator, SageMaker, leaderboard, or self-hosted cloud deployment: use `training-code/` and `aws-solutions/deepracer-on-aws`.
   - Device setup, update, SSH, or OS stack questions: start with the AWS vehicle update docs and `aws-deepracer-launcher/getting-started.md`.
2. Read `references/source-map.md` before answering or editing. It contains the source map, known stack versions, and submodule layout.
3. Prefer upstream submodule code over copying snippets into this repository. Keep local changes in this wrapper project limited to notes, indexes, and skill guidance unless the user explicitly asks to patch an upstream checkout.
4. For vehicle-side implementation tasks, assume the target stack is Ubuntu 20.04, ROS2 Foxy, Intel OpenVINO 2021.1.110, and Python 3.8 unless the user proves the device is different.
5. For physical vehicle operations, call out destructive steps before recommending them. Updating the vehicle to the ROS2 stack wipes device data.

## Common Entry Points

- Vehicle launcher and development workflow: `vehicle-code/aws-deepracer-launcher`.
- ROS Navigation integration and simulation artifacts: `vehicle-code/aws-deepracer`.
- Camera, LiDAR fusion, inference, navigation, and servo control: `vehicle-code/aws-deepracer-*-pkg`.
- Device console backend APIs: `vehicle-code/aws-deepracer-webserver-pkg`.
- Sample applications: `vehicle-code/aws-deepracer-follow-the-leader-sample-project`, `vehicle-code/aws-deepracer-mapping-sample-project`, and `vehicle-code/aws-deepracer-offroad-sample-project`.
- Self-hosted cloud training and racing solution: `training-code/deepracer-on-aws`.
- Reinforcement-learning environment and simulator libraries: `training-code/deepsim`, `training-code/deepracer-env`, `training-code/ude`, and related bridge packages.

## Git Submodule Handling

When this repository is freshly cloned, initialize submodules before inspecting code:

```bash
git submodule update --init --recursive
```

To refresh all upstream pointers for investigation, fetch inside submodules first and update this wrapper only when the user wants to record new pinned commits.
