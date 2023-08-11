#!/bin/bash

# This script will generate the protobuf bindings based on the `unified_planning.proto` file.

set -e

SCRIPTS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd ${SCRIPTS_DIR}/up_graphene_engine/grpc_io/

echo "Generating python bindings with protoc"
python3 -m grpc_tools.protoc --version

# generate bindings for protobuf and gRPC in the grpc_io folder
python3 -m grpc_tools.protoc -I. --python_out=./ --grpc_python_out=./ graphene_engine.proto

# change the relative import to an absolute one in the gRPC module
sed -i "s/import graphene_engine_pb2 as graphene__engine__pb2/import up_graphene_engine.grpc_io.graphene_engine_pb2 as graphene__engine__pb2/g" ./graphene_engine_pb2_grpc.py
