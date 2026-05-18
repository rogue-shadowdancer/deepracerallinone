# AWS DeepRacer Open Source Source Map

This reference maps the public AWS DeepRacer code and documentation ecosystem into vehicle-side and training-side areas. Use it to decide which upstream repository to inspect first.

## Primary Documentation

| Source | URL | Use |
| --- | --- | --- |
| DeepRacer on AWS implementation guide | https://docs.aws.amazon.com/solutions/latest/deepracer-on-aws/deploy-using-aws-launch-wizard.html | Deploy the self-hosted AWS Solution through AWS Launch Wizard. |
| DeepRacer on AWS solution page | https://docs.aws.amazon.com/solutions/deepracer-on-aws/ | Architecture and deployment entry point for the AWS Solution. |
| DeepRacer on AWS source | https://github.com/aws-solutions/deepracer-on-aws | Cloud-side training, evaluation, model import/export, website, API, CDK, and workflow code. |
| AWS DeepRacer GitHub organization | https://github.com/aws-deepracer | Official vehicle-side ROS2 packages, sample projects, simulator libraries, and notebooks. |
| ROS2 open-source announcement | https://aws.amazon.com/blogs/opensource/aws-deepracer-is-now-open-source-and-ready-to-hit-the-road-with-ros-2/ | Confirms AWS open-sourced vehicle code and released ROS2 packages and sample projects. |
| Device software open-source blog | https://aws.amazon.com/blogs/machine-learning/aws-deepracer-device-software-now-open-source/ | Walkthrough for Follow the Leader and vehicle-side experimentation. |
| Launcher getting started | https://github.com/aws-deepracer/aws-deepracer-launcher/blob/main/getting-started.md | Main vehicle-side build and run guide. |
| Update vehicle stack | https://docs.aws.amazon.com/solutions/latest/deepracer-on-aws/update-and-restore-vehicle.html | Update to Ubuntu 20.04, ROS2 Foxy, OpenVINO 2021.1.110, and Python 3.8. |

## Vehicle-Side Code

Official vehicle code is open source in the `aws-deepracer` GitHub organization. AWS describes the vehicle as an Ubuntu-based computer running ROS, with ROS2 Foxy as the open-source stack for current projects.

The local `vehicle-code/` folder pins these repositories as Git submodules:

| Local path | Upstream | Role |
| --- | --- | --- |
| `vehicle-code/aws-deepracer-launcher` | https://github.com/aws-deepracer/aws-deepracer-launcher | Core launcher, dependency installer, build workflow, and ROS2 launch entry point. |
| `vehicle-code/aws-deepracer` | https://github.com/aws-deepracer/aws-deepracer | ROS Navigation integration, simulation artifacts, Gazebo description, and navigation examples. |
| `vehicle-code/aws-deepracer-camera-pkg` | https://github.com/aws-deepracer/aws-deepracer-camera-pkg | Camera node for one or two RGB cameras. |
| `vehicle-code/aws-deepracer-ctrl-pkg` | https://github.com/aws-deepracer/aws-deepracer-ctrl-pkg | Control node for manual, autonomous, calibration, and other modes. |
| `vehicle-code/aws-deepracer-inference-pkg` | https://github.com/aws-deepracer/aws-deepracer-inference-pkg | OpenVINO inference node for selected ML models. |
| `vehicle-code/aws-deepracer-navigation-pkg` | https://github.com/aws-deepracer/aws-deepracer-navigation-pkg | Converts inference results and action space into steering and throttle commands. |
| `vehicle-code/aws-deepracer-servo-pkg` | https://github.com/aws-deepracer/aws-deepracer-servo-pkg | Maps throttle and steering ratios to raw PWM values for vehicle motion. |
| `vehicle-code/aws-deepracer-webserver-pkg` | https://github.com/aws-deepracer/aws-deepracer-webserver-pkg | Flask-backed vehicle console APIs and ROS service clients/subscribers. |
| `vehicle-code/aws-deepracer-systems-pkg` | https://github.com/aws-deepracer/aws-deepracer-systems-pkg | Software update, model loader, OTG, network monitor, and system support nodes. |
| `vehicle-code/aws-deepracer-interfaces-pkg` | https://github.com/aws-deepracer/aws-deepracer-interfaces-pkg | Custom ROS2 service and message definitions used by the core application. |
| `vehicle-code/aws-deepracer-sensor-fusion-pkg` | https://github.com/aws-deepracer/aws-deepracer-sensor-fusion-pkg | Combines camera and LiDAR messages into fused sensor messages. |
| `vehicle-code/aws-deepracer-model-optimizer-pkg` | https://github.com/aws-deepracer/aws-deepracer-model-optimizer-pkg | Runs OpenVINO Model Optimizer for DeepRacer RL model artifacts. |
| `vehicle-code/aws-deepracer-usb-monitor-pkg` | https://github.com/aws-deepracer/aws-deepracer-usb-monitor-pkg | Watches USB drive connect/disconnect events and expected files. |
| `vehicle-code/aws-deepracer-status-led-pkg` | https://github.com/aws-deepracer/aws-deepracer-status-led-pkg | Controls Wi-Fi and power status LED effects. |
| `vehicle-code/aws-deepracer-i2c-pkg` | https://github.com/aws-deepracer/aws-deepracer-i2c-pkg | Battery level node over I2C. |
| `vehicle-code/aws-deepracer-device-info-pkg` | https://github.com/aws-deepracer/aws-deepracer-device-info-pkg | Hardware and software version reporting. |
| `vehicle-code/aws-deepracer-follow-the-leader-sample-project` | https://github.com/aws-deepracer/aws-deepracer-follow-the-leader-sample-project | Object-detection based Follow the Leader sample application. |
| `vehicle-code/aws-deepracer-mapping-sample-project` | https://github.com/aws-deepracer/aws-deepracer-mapping-sample-project | SLAM mapping sample using an Intel RealSense depth camera. |
| `vehicle-code/aws-deepracer-offroad-sample-project` | https://github.com/aws-deepracer/aws-deepracer-offroad-sample-project | QR-code waypoint navigation sample. |

## Training And Simulation Code

The local `training-code/` folder pins the cloud, simulator, and RL environment repositories as Git submodules:

| Local path | Upstream | Role |
| --- | --- | --- |
| `training-code/deepracer-on-aws` | https://github.com/aws-solutions/deepracer-on-aws | AWS Solution for self-hosted training, evaluation, model import/export, website, APIs, CDK, and workflows. |
| `training-code/deepsim` | https://github.com/aws-deepracer/deepsim | Open-source reinforcement learning environment build toolkit for ROS and Gazebo. |
| `training-code/deepracer-env` | https://github.com/aws-deepracer/deepracer-env | Python interface for the RL Lab DeepRacer environment. |
| `training-code/deepracer-env-config` | https://github.com/aws-deepracer/deepracer-env-config | Python library for manipulating RL Lab DeepRacer environment configurations over the UDE side channel. |
| `training-code/deepracer-env-state` | https://github.com/aws-deepracer/deepracer-env-state | RL Lab DeepRacer environment state utilities. |
| `training-code/deepracer-track-geometry` | https://github.com/aws-deepracer/deepracer-track-geometry | Track geometry access package. |
| `training-code/ude` | https://github.com/aws-deepracer/ude | Unified Distributed Environment library for virtualizing reinforcement-learning environments. |
| `training-code/ude-gym-bridge` | https://github.com/aws-deepracer/ude-gym-bridge | Bridge between UDE and OpenAI Gym. |
| `training-code/ude-ros-bridge` | https://github.com/aws-deepracer/ude-ros-bridge | Bridge between UDE and ROS. |
| `training-code/aws-deepracer-notebooks` | https://github.com/aws-deepracer/aws-deepracer-notebooks | Notebooks for deeper training, simulation, and RL algorithm control. |
| `training-code/deepracer-compat-reward-function` | https://github.com/aws-deepracer/deepracer-compat-reward-function | Compatibility helpers for reward functions. |

## Operational Notes

- Use `git clone --recurse-submodules` or `git submodule update --init --recursive` to materialize upstream code.
- The vehicle open-source stack expects Ubuntu 20.04 Focal Fossa, ROS2 Foxy Fitzroy, Intel OpenVINO 2021.1.110, and Python 3.8.
- Updating a physical AWS DeepRacer vehicle to the Ubuntu 20.04/ROS2 stack wipes all existing data on the device.
- Build vehicle-side packages on the device when changing core packages or creating new ROS2 packages.
- Stop `deepracer-core.service` before running a locally built launcher stack on the vehicle.
