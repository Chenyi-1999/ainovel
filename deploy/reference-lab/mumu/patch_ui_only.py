"""Apply a guarded evaluation-only patch; never import or execute upstream code."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import sys

SOURCE_COMMIT = "743e5abec18beb8d73426527e6579538053bc6fd"
MEMORY_SHA256 = "fa83322537c9165a4e7449fcaf312cf7ca02e8ae7d0181b751b0eff5d051980d"
REQUIREMENTS_SHA256 = "1dd3cfb42d9a8f535f30a350fd8e3d57bd89985e51a89c81c0fbad3cfb98cbad"
OMITTED_PACKAGES = {"chromadb", "numpy", "onnxruntime", "tokenizers", "filelock"}


def checked_text(path: Path, expected_sha: str) -> str:
    # Git may use CRLF on Windows; canonicalize only line endings for the guard.
    source = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != expected_sha:
        raise ValueError(f"Unsupported upstream file: {path}; review against {SOURCE_COMMIT}")
    return source


def patch_memory(source: str) -> str:
    source = source.replace("import chromadb\n", "", 1)
    source = source.replace("from app.services.onnx_embedding import OnnxEmbeddingModel\n", "", 1)
    marker = "logger = get_logger(__name__)\n"
    addition = '''
# Evaluation image only: no vector engine, model import, or model download.
UI_ONLY = os.getenv("MUMU_UI_ONLY", "").lower() == "true"
if not UI_ONLY:
    import chromadb
    from app.services.onnx_embedding import OnnxEmbeddingModel


class _UnavailableVectorBackend:
    def __getattr__(self, name):
        raise RuntimeError("Vector memory/knowledge indexing is disabled in this UI-only evaluation")

'''
    if source.count(marker) != 1:
        raise ValueError("Memory-service logger marker changed")
    source = source.replace(marker, marker + addition, 1)
    marker = "        if self._initialized:\n            return\n"
    addition = '''
        if UI_ONLY:
            self.client = _UnavailableVectorBackend()
            self.embedding_model = _UnavailableVectorBackend()
            self._initialized = True
            logger.warning("UI-only evaluation: vector memory and embedding are disabled")
            return
'''
    if source.count(marker) != 1:
        raise ValueError("Memory-service initialization marker changed")
    source = source.replace(marker, marker + addition, 1)
    ast.parse(source)
    return source


def patch_requirements(source: str) -> str:
    retained = []
    removed = set()
    for line in source.splitlines():
        package = re.split(r"[<>=!~\[\s]", line.strip(), maxsplit=1)[0].lower()
        if package in OMITTED_PACKAGES:
            removed.add(package)
        else:
            retained.append(line)
    if removed != OMITTED_PACKAGES:
        raise ValueError(f"Embedding requirement list changed: {removed}")
    return "\n".join(retained) + "\n"


def apply(backend: Path) -> None:
    memory_path = backend / "app/services/memory_service.py"
    requirements_path = backend / "requirements.txt"
    memory = patch_memory(checked_text(memory_path, MEMORY_SHA256))
    requirements = patch_requirements(checked_text(requirements_path, REQUIREMENTS_SHA256))
    memory_path.write_text(memory, encoding="utf-8", newline="\n")
    requirements_path.write_text(requirements, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    apply(Path(sys.argv[1]))
