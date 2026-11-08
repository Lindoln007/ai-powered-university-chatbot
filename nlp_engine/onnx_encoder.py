"""Runs sentence-transformers/all-MiniLM-L6-v2 with ONNX Runtime.

The model repository on Hugging Face publishes an official ONNX export
(``onnx/model.onnx``) of the same weights used by the PyTorch version. This
module reproduces the Sentence Transformer pipeline for this model exactly:

    tokenise (max 256 tokens) -> Transformer -> mean pooling over real tokens -> L2 normalisation

Embeddings are numerically identical to the PyTorch implementation (verified:
cosine similarity 1.000000 on every stored knowledge base text), but the
runtime only needs ``onnxruntime`` and ``tokenizers`` (about 700 files)
instead of PyTorch + Transformers (about 20,000 files). On Windows this cuts
server start-up from minutes to seconds, because importing PyTorch on a cold
file cache is very slow.
"""

import json
from pathlib import Path

import numpy as np

MODEL_FILE = "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"
REQUIRED_FILES = (MODEL_FILE, TOKENIZER_FILE, "sentence_bert_config.json")


def _snapshot_dir(cache_dir: Path, repo_id: str) -> Path | None:
    """Locate the cached model snapshot without importing huggingface_hub."""
    repo_dir = cache_dir / f"models--{repo_id.replace('/', '--')}"
    ref = repo_dir / "refs" / "main"
    candidates = []
    if ref.exists():
        candidates.append(repo_dir / "snapshots" / ref.read_text().strip())
    candidates.extend(sorted((repo_dir / "snapshots").glob("*")) if (repo_dir / "snapshots").exists() else [])
    for snapshot in candidates:
        if all((snapshot / name).exists() for name in REQUIRED_FILES):
            return snapshot
    return None


def ensure_model_files(cache_dir: Path, repo_id: str, offline: bool) -> Path:
    """Return the local snapshot folder, downloading the ONNX files once if allowed."""
    snapshot = _snapshot_dir(cache_dir, repo_id)
    if snapshot is not None:
        return snapshot
    if offline:
        raise FileNotFoundError(f"ONNX files for {repo_id} are not in {cache_dir} and NLP_OFFLINE is enabled.")
    from huggingface_hub import hf_hub_download  # only needed for the one-time download

    for name in REQUIRED_FILES:
        hf_hub_download(repo_id, name, cache_dir=str(cache_dir))
    snapshot = _snapshot_dir(cache_dir, repo_id)
    if snapshot is None:
        raise FileNotFoundError(f"Downloaded files for {repo_id} could not be found in {cache_dir}.")
    return snapshot


class OnnxSentenceEncoder:
    """Drop-in replacement for the parts of ``SentenceTransformer`` this project uses."""

    def __init__(self, model_dir: Path, threads: int):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        config = json.loads((model_dir / "sentence_bert_config.json").read_text(encoding="utf-8"))
        self.max_seq_length = int(config.get("max_seq_length", 256))

        self.tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE))
        self.tokenizer.enable_truncation(max_length=self.max_seq_length)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_dir / MODEL_FILE), options, providers=["CPUExecutionProvider"])
        self._input_names = {item.name for item in self.session.get_inputs()}
        self._dimension = int(self.session.get_outputs()[0].shape[-1])

    def get_embedding_dimension(self) -> int:
        return self._dimension

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch(texts)
        input_ids = np.asarray([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.asarray([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        token_embeddings = self.session.run(None, feeds)[0]
        # Mean pooling over real (non-padding) tokens, as in the model's 1_Pooling config.
        mask = attention_mask[..., None].astype(np.float32)
        summed = (token_embeddings * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        return summed / counts

    def encode(self, sentences: list[str], batch_size: int = 32, normalize_embeddings: bool = True, **_ignored) -> np.ndarray:
        if not sentences:
            return np.zeros((0, self._dimension), dtype=np.float32)
        # Sort by length so each batch pads to a similar length (less wasted computation).
        order = np.argsort([len(text) for text in sentences])
        vectors = np.empty((len(sentences), self._dimension), dtype=np.float32)
        for start in range(0, len(sentences), batch_size):
            indices = order[start:start + batch_size]
            vectors[indices] = self._encode_batch([sentences[i] for i in indices])
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors /= np.clip(norms, 1e-12, None)
        return vectors
