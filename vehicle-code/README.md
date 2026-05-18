# Vehicle Code

This folder contains Git submodules for official AWS DeepRacer vehicle-side ROS2 and device-code repositories.

Use this area for physical vehicle behavior, ROS2 nodes, sensors, model inference, navigation, servo control, device console APIs, system services, and sample applications.

Initialize after cloning:

```bash
git submodule update --init --recursive vehicle-code
```

Main starting points:

- `aws-deepracer-launcher` - build and launch the core ROS2 application on the vehicle.
- `aws-deepracer` - ROS Navigation integration and simulation artifacts.
- `aws-deepracer-*-pkg` - focused ROS2 packages for camera, control, inference, navigation, servo, webserver, systems, and support nodes.
- `aws-deepracer-follow-the-leader-sample-project`, `aws-deepracer-mapping-sample-project`, `aws-deepracer-offroad-sample-project` - sample applications.
