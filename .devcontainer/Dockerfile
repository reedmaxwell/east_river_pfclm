# ParFlow with CLM, built from a release tag, for GitHub Codespaces / VS Code dev containers.
# Untested on Codespaces as of 2026-09-13: expect to adjust package names if the base image moves.
FROM mcr.microsoft.com/devcontainers/python:3.11
ARG PARFLOW_VERSION=v3.15.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake gfortran libopenmpi-dev openmpi-bin libhypre-dev tcl-dev libtirpc-dev \
    && rm -rf /var/lib/apt/lists/*
ENV PARFLOW_DIR=/opt/parflow
RUN git clone --depth 1 --branch ${PARFLOW_VERSION} https://github.com/parflow/parflow.git /tmp/parflow \
    && cmake -S /tmp/parflow -B /tmp/parflow/build -DCMAKE_INSTALL_PREFIX=${PARFLOW_DIR} -DCMAKE_BUILD_TYPE=Release -DPARFLOW_AMPS_LAYER=mpi1 \
         -DPARFLOW_HAVE_CLM=ON -DHYPRE_ROOT=/usr -DPARFLOW_ENABLE_TIMING=TRUE -DPARFLOW_ENABLE_PYTHON=ON \
    && cmake --build /tmp/parflow/build --target install -j 4 && rm -rf /tmp/parflow
ENV PATH=${PARFLOW_DIR}/bin:${PATH}
RUN pip install --no-cache-dir pftools numpy pandas matplotlib xarray netCDF4 hf_hydrodata subsettools
