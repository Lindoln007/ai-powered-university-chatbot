"""Loads the pre-trained Sentence Transformer model once per process.

The model (sentence-transformers/all-MiniLM-L6-v2) is downloaded from the
Hugging Face Hub the first time it is needed and cached in
``settings.NLP_MODEL_CACHE_DIR``. Afterwards it runs completely locally on
the CPU. There is deliberately no fallback to any external inference API.

Two interchangeable runtimes are supported (``NLP_BACKEND``):

* ``onnx`` (default): the model's official ONNX export run by ONNX Runtime.
  Same weights and identical embeddings, but starts in about a second because
  it does not import PyTorch.
* ``torch``: the ``sentence-transformers`` library on PyTorch.
"""

import logging
import os
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_model = None
_load_seconds = None
_load_error = None
_warming_up = False
_lock = threading.Lock()
_warmup_steps = []


class ModelUnavailableError(RuntimeError):
    """Raised when the local Sentence Transformer model cannot be loaded."""


INSTALL_HINT = (
    "The Sentence Transformer model '{name}' could not be loaded from '{cache}'. "
    "Install the dependencies (pip install -r requirements.txt) and download the model once "
    "with an internet connection by running: python manage.py download_model. "
    "After that the model works offline (set NLP_OFFLINE=true to forbid network access)."
)


def cpu_threads() -> int:
    """Threads for inference: physical cores (max 4) unless configured."""
    return settings.NLP_THREADS or max(1, min(4, (os.cpu_count() or 2) // 2))


def _configure_environment():
    if settings.NLP_OFFLINE:
        # Never contact the Hugging Face Hub: load strictly from the local cache.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _load_onnx(name, cache_dir):
    from .onnx_encoder import OnnxSentenceEncoder, ensure_model_files

    model_dir = ensure_model_files(cache_dir, name, offline=settings.NLP_OFFLINE)
    return OnnxSentenceEncoder(model_dir, threads=cpu_threads())


def _load_torch(name, cache_dir):
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(cpu_threads())
    return SentenceTransformer(name, device=settings.NLP_DEVICE, cache_folder=str(cache_dir),
                               local_files_only=settings.NLP_OFFLINE)


LOADERS = {"onnx": _load_onnx, "torch": _load_torch}


def _load_model():
    _configure_environment()
    name = settings.NLP_MODEL_NAME
    cache_dir = settings.NLP_MODEL_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    backend = settings.NLP_BACKEND
    if backend not in LOADERS:
        raise ModelUnavailableError(f"Unknown NLP_BACKEND '{backend}'. Use one of: {', '.join(LOADERS)}.")
    started = time.perf_counter()
    try:
        model = LOADERS[backend](name, cache_dir)
    except ImportError as exc:
        raise ModelUnavailableError(
            f"The packages for the '{backend}' backend are not installed. Run: pip install -r requirements.txt"
        ) from exc
    except Exception as exc:
        logger.error("Failed to load Sentence Transformer model %s (%s backend): %s", name, backend, exc)
        raise ModelUnavailableError(INSTALL_HINT.format(name=name, cache=cache_dir)) from exc

    global _load_seconds
    _load_seconds = round(time.perf_counter() - started, 2)
    logger.info("Loaded %s with the %s backend on CPU in %.2fs", name, backend, _load_seconds)
    return model


def get_model():
    """Return the shared model instance, loading it on first use (thread safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = _load_model()
    return _model


def register_warmup_step(step) -> None:
    """Let other apps add work (such as building the search index) to the start-up warm-up."""
    _warmup_steps.append(step)


def warm_up_in_background() -> None:
    """Load the model, intent examples and search index in a background thread at start-up."""
    if not settings.NLP_PRELOAD_MODEL:
        return

    def _warm():
        global _warming_up, _load_error
        _warming_up = True
        started = time.perf_counter()
        try:
            from .intent_classifier import get_intent_classifier

            get_model()
            get_intent_classifier()._ensure_index()
            for step in _warmup_steps:
                step()
            logger.info("NLP engine ready in %.2fs.", time.perf_counter() - started)
        except Exception as exc:  # the server keeps running; requests report the problem
            _load_error = str(exc)
            logger.warning("NLP warm-up failed: %s", exc)
        finally:
            _warming_up = False

    threading.Thread(target=_warm, name="nlp-warmup", daemon=True).start()


def is_model_loaded() -> bool:
    return _model is not None


def embedding_dimension(model) -> int:
    # Renamed in newer sentence-transformers releases; support both (and the ONNX encoder).
    getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
    return getter()


def model_status() -> dict:
    if is_model_loaded():
        state = "ready"
    elif _warming_up:
        state = "loading"
    elif _load_error:
        state = "error"
    else:
        state = "not_loaded"  # loads on the first question
    status = {
        "name": settings.NLP_MODEL_NAME,
        "backend": settings.NLP_BACKEND,
        "status": state,
        "loaded": is_model_loaded(),
        "device": "cpu",
        "offline_mode": settings.NLP_OFFLINE,
    }
    if _model is not None:
        status["embedding_dimension"] = embedding_dimension(_model)
        status["load_seconds"] = _load_seconds
    return status
