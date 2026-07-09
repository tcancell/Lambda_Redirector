#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKOV_VENV="${ROOT_DIR}/.venv-checkov"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CHECKOV_VERSION="${CHECKOV_VERSION:-3.3.7}"
PIP_CACHE_DIR="${PIP_CACHE_DIR:-/tmp/lambda-redirect-pip-cache}"
export PIP_CACHE_DIR

if [[ ! -x "${CHECKOV_VENV}/bin/checkov" ]]; then
  "${PYTHON_BIN}" -m venv "${CHECKOV_VENV}"
  "${CHECKOV_VENV}/bin/python" -m pip install --upgrade 'pip<26'
  "${CHECKOV_VENV}/bin/python" -m pip install "checkov==${CHECKOV_VERSION}" 'packaging<24.0,>=23.0'
fi

"${CHECKOV_VENV}/bin/python" -m checkov.main -d "${ROOT_DIR}/terraform" --framework terraform --quiet
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-/tmp/trivy-cache}" trivy config --severity HIGH,CRITICAL --skip-dirs terraform/.terraform,.venv-checkov "${ROOT_DIR}"
