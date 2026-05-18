# Training Code

This folder contains Git submodules for DeepRacer training, simulation, cloud deployment, notebooks, and reinforcement-learning environment libraries.

Use this area for self-hosted DeepRacer on AWS deployments, reward functions, training and evaluation workflows, model import/export, simulator libraries, UDE bridges, and notebooks.

Initialize after cloning:

```bash
git submodule update --init --recursive training-code
```

Main starting points:

- `deepracer-on-aws` - AWS Solution for training and evaluating DeepRacer models in a self-hosted AWS account.
- `deepsim`, `deepracer-env`, `deepracer-env-config`, `deepracer-env-state`, `deepracer-track-geometry` - simulator and environment libraries.
- `ude`, `ude-gym-bridge`, `ude-ros-bridge` - Unified Distributed Environment packages and bridges.
- `aws-deepracer-notebooks` - notebooks for deeper control over training and simulation.
