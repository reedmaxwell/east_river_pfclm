#!/bin/bash
# Download the corrected WY2017 forcing (about 720 MB unpacked) from the repository's release
# assets into inputs/forcing/wy2017.  Run from the repository root.
set -e
URL="https://github.com/reedmaxwell/east_river_pfclm/releases/download/v1.0/east_river_forcing_wy2017.tar.gz"
mkdir -p inputs/forcing
if [ -f inputs/forcing/wy2017/CW3E.APCP.000001_to_000024.pfb ]; then echo "forcing already present"; exit 0; fi
echo "downloading the forcing tarball ..."
curl -L -o inputs/forcing/east_river_forcing_wy2017.tar.gz "$URL"
tar xzf inputs/forcing/east_river_forcing_wy2017.tar.gz -C inputs/forcing
mv inputs/forcing/wy2017_tval inputs/forcing/wy2017 2>/dev/null || true
rm inputs/forcing/east_river_forcing_wy2017.tar.gz
echo "forcing ready: $(ls inputs/forcing/wy2017 | wc -l) files"
