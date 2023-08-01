#!/bin/bash

# This script will generate the protobuf bindings based on the `unified_planning.proto` file.

set -e

SCRIPTS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd ${SCRIPTS_DIR}/up_grafene_engine/grpc_io/

echo "Generating python bindings with protoc"
python3 -m grpc_tools.protoc --version

# generate bindings for protobuf and gRPC in the grpc_io folder
python3 -m grpc_tools.protoc -I. --python_out=./ --grpc_python_out=./ grafene_engine.proto

# change the relative import to an absolute one in the gRPC module
sed -i "s/import grafene_engine_pb2 as grafene__engine__pb2/import up_grafene_engine.grpc_io.grafene_engine_pb2 as grafene__engine__pb2/g" ./grafene_engine_pb2_grpc.py
