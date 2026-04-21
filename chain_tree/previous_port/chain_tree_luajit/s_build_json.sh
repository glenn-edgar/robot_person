#!/bin/bash
# s_build_yaml.sh - Run a ChainTree LuaJIT DSL test and generate YAML output
#
# Usage: ./s_build_yaml.sh <lua_test_file> <output_directory>
#
# Example: ./s_build_yaml.sh dsl_tests/incremental_build/incremental_build.lua dsl_tests/test_all
#   -> runs incremental_build.lua with output: dsl_tests/test_all/incremental_build.yaml

if [ $# -ne 2 ]; then
    echo "Usage: $0 <lua_test_file> <output_directory>"
    echo "  lua_test_file   : path to the .lua test file (e.g. dsl_tests/incremental_build/incremental_build.lua)"
    echo "  output_directory: directory for the .yaml output (e.g. dsl_tests/test_all)"
    exit 1
fi

LUA_TEST_FILE="$1"
OUTPUT_DIR="$2"

# Validate test file exists
if [ ! -f "$LUA_TEST_FILE" ]; then
    echo "Error: Lua test file not found: $LUA_TEST_FILE"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Derive yaml filename from lua filename: test_file.lua -> test_file.yaml
BASENAME=$(basename "$LUA_TEST_FILE" .lua)
YAML_FILE="${OUTPUT_DIR}/${BASENAME}.yaml"

# Get the project root (directory containing lua_dsl/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Set LUA_PATH so require("lua_support.xxx") and require("lua_dsl.xxx") resolve correctly
export LUA_PATH="${SCRIPT_DIR}/lua_dsl/?.lua;${SCRIPT_DIR}/lua_dsl/?/init.lua;${SCRIPT_DIR}/?.lua;${SCRIPT_DIR}/?/init.lua;;"

echo "Running: $LUA_TEST_FILE"
echo "Output:  $YAML_FILE"

luajit "$LUA_TEST_FILE" "$YAML_FILE"

