#!/usr/bin/env bash
# quantize_ocr.sh — Re-create the deepseek-ocr model with Q4_K_M quantization.
#
# The default deepseek-ocr model ships at F16 precision (6.7GB).
# Q4_K_M reduces this to ~2GB with negligible OCR quality loss and
# 2-3x faster inference on Apple Silicon.
#
# Usage:
#   ./scripts/quantize_ocr.sh
#
# Prerequisites:
#   - Ollama must be running (locally or via docker compose)
#   - The deepseek-ocr model must already be pulled

set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
MODEL_NAME="deepseek-ocr"
QUANTIZED_NAME="deepseek-ocr-q4"
TMPDIR="$(mktemp -d)"
MODELFILE="${TMPDIR}/Modelfile"

echo "==> Exporting Modelfile for ${MODEL_NAME}..."
ollama show "${MODEL_NAME}" --modelfile > "${MODELFILE}" 2>/dev/null

# Verify we got a valid Modelfile
if ! grep -q "^FROM" "${MODELFILE}"; then
    echo "ERROR: Could not export Modelfile for ${MODEL_NAME}."
    echo "Make sure the model is pulled: ollama pull ${MODEL_NAME}"
    rm -rf "${TMPDIR}"
    exit 1
fi

echo "==> Creating quantized model ${QUANTIZED_NAME} (Q4_K_M)..."
# Insert PARAMETER stop and quantization directive
cat >> "${MODELFILE}" <<'EOF'

# Quantize to Q4_K_M for faster inference
PARAMETER num_ctx 2048
EOF

# Create the quantized model
ollama create "${QUANTIZED_NAME}" -f "${MODELFILE}" --quantize q4_K_M

echo "==> Verifying ${QUANTIZED_NAME}..."
ollama list | grep "${QUANTIZED_NAME}" && echo "SUCCESS: Model created." || echo "WARNING: Model not found in list."

echo ""
echo "To use the quantized model, update your teacher's OCR model setting"
echo "to '${QUANTIZED_NAME}' in the web UI, or set OCR_MODEL=${QUANTIZED_NAME}"
echo "in your .env file."

rm -rf "${TMPDIR}"
