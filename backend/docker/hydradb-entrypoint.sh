#!/usr/bin/env bash
# Mirrors the local-development configuration from HydraDB's README, with the token taken from the environment.
set -euo pipefail
: "${HYDRADB_TOKEN:?Set HYDRADB_TOKEN (32+ characters)}"
if [ "${#HYDRADB_TOKEN}" -lt 32 ]; then echo "HYDRADB_TOKEN must be at least 32 characters" >&2; exit 1; fi
mkdir -p /data/store /data/cache
printf '%s\n' "$HYDRADB_TOKEN" > /data/auth-token
export CLOUD_PROVIDER=local LOCAL_PATH=/data/store
export GRAPH_NAMESPACE=default GRAPH_ID=default GRAPH_CELL_ID=cell-0 GRAPH_CELLS=cell-0 GRAPH_NODE_ID=node-0
export GRAPH_BOLT_NODE_ADDRESSES="node-0=0.0.0.0:7687" GRAPH_ADVERTISED_BOLT_ADDR="hydradb:7687"
export GRAPH_DATA_CACHE_DIR=/data/cache GRAPH_AUTH_TOKEN_FILE=/data/auth-token
# Plaintext is acceptable ONLY because port 7687 is never published outside the compose network.
export GRAPH_ALLOW_PLAINTEXT=true RUST_MIN_STACK=33554432
exec graph-node
