#!/bin/sh
set -eu

data_root="${GIGAAM_DATA_DIR:-/data}"
export GIGAAM_DATA_DIR="$data_root"
export GIGAAM_RUNTIME_DIR="${GIGAAM_RUNTIME_DIR:-$data_root/runtimes}"
export GIGAAM_PYTORCH_MODEL_DIR="${GIGAAM_PYTORCH_MODEL_DIR:-$data_root/models/gigaam}"
export HF_HOME="${HF_HOME:-$data_root/models/huggingface}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export TORCH_HOME="${TORCH_HOME:-$data_root/models/torch}"
export NEMO_HOME="${NEMO_HOME:-$data_root/models/nemo}"
export ONNX_MODEL_DIR="${ONNX_MODEL_DIR:-$data_root/models/onnx}"
export GIGAAM_DEEPFILTER_DIR="${GIGAAM_DEEPFILTER_DIR:-$data_root/models/deepfilter}"
export HOME="${GIGAAM_HOME:-$data_root/runtime-home}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/tmp/cache}"

# Docker создаёт новый bind mount как root:root. Перед запуском приложения
# создаём только известные writable-каталоги и отдаём их приложению без
# рекурсивного chown уже скачанных моделей.
if [ "$(id -u)" = "0" ]; then
    mkdir -p \
        "$data_root" \
        "$GIGAAM_RUNTIME_DIR" \
        "$GIGAAM_PYTORCH_MODEL_DIR" \
        "$HF_HOME" \
        "$HUGGINGFACE_HUB_CACHE" \
        "$TORCH_HOME" \
        "$NEMO_HOME" \
        "$ONNX_MODEL_DIR" \
        "$GIGAAM_DEEPFILTER_DIR" \
        "$HOME" \
        "$XDG_CACHE_HOME"
    chown gigaam:gigaam \
        "$data_root" \
        "$GIGAAM_RUNTIME_DIR" \
        "$GIGAAM_PYTORCH_MODEL_DIR" \
        "$HF_HOME" \
        "$HUGGINGFACE_HUB_CACHE" \
        "$TORCH_HOME" \
        "$NEMO_HOME" \
        "$ONNX_MODEL_DIR" \
        "$GIGAAM_DEEPFILTER_DIR" \
        "$HOME" \
        "$XDG_CACHE_HOME"
    exec gosu gigaam "$@"
fi

exec "$@"
