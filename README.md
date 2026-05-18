# DeepRacer All In One

This repository is a lightweight index for AWS DeepRacer open-source materials. It keeps upstream source code as Git submodules instead of copying code into this repository.

## Layout

- `deepracer-open-source-navigator/` - Codex skill skeleton for finding the right DeepRacer repo, docs, and setup path.
- `vehicle-code/` - Official AWS DeepRacer vehicle-side ROS2 and device-code submodules.
- `training-code/` - DeepRacer on AWS, simulator, RL environment, and notebook submodules.

## Clone

Use recursive submodule cloning:

```bash
git clone --recurse-submodules https://github.com/rogue-shadowdancer/deepracerallinone.git
```

If already cloned:

```bash
git submodule update --init --recursive
```

## Upstream Sources

Official vehicle-side code is open source under the AWS DeepRacer GitHub organization:

- https://github.com/aws-deepracer
- https://github.com/aws-solutions/deepracer-on-aws

See `deepracer-open-source-navigator/references/source-map.md` for the curated source map.
