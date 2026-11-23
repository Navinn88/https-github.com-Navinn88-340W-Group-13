"""
Hallucination detection with Kernel Language Entropy (KLE).

Reference: Nikitin, Kossen, Gal & Marttinen. "Kernel Language Entropy: Fine-grained
Uncertainty Quantification for LLMs from Semantic Similarities". NeurIPS 2024.
https://arxiv.org/abs/2405.20003

The idea: if the model "knows" the answer, independently sampled answers to the same
prompt mean the same thing. If it is making things up, the samples disagree. KLE turns
that intuition into a number:

1. Sample N answers to the same prompt at a high temperature.
2. Build a semantic graph over the answers. For every ordered pair (i, j) a natural
   language inference (NLI) model decides whether answer i entails answer j. The edge
   weight is w_ij = f(i -> j) + f(j -> i), where f is 1 for entailment, 0.5 for
   neutral and 0 for contradiction (the weighting used in the paper).
3. Take the graph Laplacian L = D - W and turn it into a heat kernel K = exp(-t L).
4. Normalise K to a unit-trace positive semidefinite matrix (a "density matrix").
5. KLE is the von Neumann entropy of that matrix: -Tr[K log K] = -sum(l * log l) over
   its eigenvalues l.

The entropy lies between 0 and log(N). All-equivalent answers give a low value. Answers
that all contradict each other give log(N). We also report the entropy divided by
log(N), which lies in [0, 1] and is what the flagging threshold is applied to.

This module only imports numpy at import time. The NLI model (sentence-transformers) is
imported lazily so the maths can be tested without the heavy dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ENTAILMENT = "entailment"
NEUTRAL = "neutral"
CONTRADICTION = "contradiction"

# f(i -> j) from the KLE paper
LABEL_WEIGHTS = {ENTAILMENT: 1.0, NEUTRAL: 0.5, CONTRADICTION: 0.0}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)


class NLIModel(Protocol):
    def predict(self, pairs: Sequence[Tuple[str, str]]) -> List[str]:
        """Return one of 'entailment', 'neutral', 'contradiction' per (premise, hypothesis) pair."""
        ...


# ---------------------------------------------------------------------------
# Maths
# ---------------------------------------------------------------------------


def semantic_weights(texts: Sequence[str], nli: NLIModel) -> np.ndarray:
    """Symmetric weight matrix W with w_ij = f(i -> j) + f(j -> i), in [0, 2]."""
    n = len(texts)
    f = np.zeros((n, n), dtype=float)

    index_pairs = []
    text_pairs = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if texts[i].strip() == texts[j].strip():
                # Identical strings entail each other; no need to ask the NLI model.
                f[i, j] = LABEL_WEIGHTS[ENTAILMENT]
                continue
            index_pairs.append((i, j))
            text_pairs.append((texts[i], texts[j]))

    if text_pairs:
        labels = nli.predict(text_pairs)
        if len(labels) != len(text_pairs):
            raise ValueError(
                "NLI model returned a different number of labels than pairs"
            )
        for (i, j), label in zip(index_pairs, labels):
            f[i, j] = LABEL_WEIGHTS[label]

    return f + f.T


def heat_kernel(weights: np.ndarray, t: float) -> np.ndarray:
    """K = exp(-t L) with L = D - W the (unnormalised) graph Laplacian."""
    w = np.asarray(weights, dtype=float)
    w = (w + w.T) / 2
    np.fill_diagonal(w, 0.0)  # self-loops cancel out in D - W anyway
    laplacian = np.diag(w.sum(axis=1)) - w
    # L is symmetric, so exp(-tL) = V diag(exp(-t * eigvals)) V^T
    eigvals, eigvecs = np.linalg.eigh(laplacian)
    return (eigvecs * np.exp(-t * eigvals)) @ eigvecs.T


def normalize_kernel(kernel: np.ndarray) -> np.ndarray:
    """K_ij / sqrt(K_ii K_jj) / N, which gives a unit-trace PSD matrix."""
    k = np.asarray(kernel, dtype=float)
    diag = np.sqrt(np.clip(np.diag(k), 1e-12, None))
    return k / np.outer(diag, diag) / k.shape[0]


def von_neumann_entropy(density: np.ndarray) -> float:
    """-Tr[rho log rho], computed from the eigenvalues of rho."""
    eigvals = np.linalg.eigvalsh(np.asarray(density, dtype=float))
    eigvals = eigvals[eigvals > 1e-12]
    return float(-(eigvals * np.log(eigvals)).sum())


def kernel_language_entropy(weights: np.ndarray, t: float = 1.0) -> float:
    """
    KLE for a semantic graph given by its weight matrix.

    The paper suggests t=0.3 as a reasonable default for short QA answers. CIRA's
    answers are long paragraphs, where NLI often says "neutral" for answers that agree.
    With t=0.3 and 5 samples, "all neutral" scores almost as high as two contradicting
    groups (normalised 0.84 vs 0.83), and even perfect agreement scores 0.42. t=1.0
    separates these much better (0.10 vs 0.45, perfect agreement ~0), so it is the
    default here. Tune it together with the threshold on your own data.
    """
    if weights.shape[0] < 2:
        return 0.0
    return von_neumann_entropy(normalize_kernel(heat_kernel(weights, t)))


def max_entropy(num_answers: int) -> float:
    return math.log(num_answers) if num_answers > 1 else 1.0


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks that some reasoning models put in the content."""
    return _THINK_BLOCK.sub("", text or "").strip()


# ---------------------------------------------------------------------------
# NLI model
# ---------------------------------------------------------------------------


class CrossEncoderNLI:
    """NLI with a sentence-transformers CrossEncoder (e.g. cross-encoder/nli-deberta-v3-small)."""

    def __init__(self, model_name: str, max_length: int = 512, batch_size: int = 16):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, max_length=max_length)
        self.batch_size = batch_size
        id2label = self.model.config.id2label
        self.labels = [str(id2label[i]).lower() for i in range(len(id2label))]
        missing = {ENTAILMENT, NEUTRAL, CONTRADICTION} - set(self.labels)
        if missing:
            raise ValueError(
                f"NLI model {model_name} must have entailment/neutral/contradiction labels, "
                f"got {self.labels}"
            )
        # Torch inference is not guaranteed to be safe across threads.
        self._lock = threading.Lock()

    def predict(self, pairs: Sequence[Tuple[str, str]]) -> List[str]:
        with self._lock:
            scores = self.model.predict(
                list(pairs),
                batch_size=self.batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        scores = np.asarray(scores).reshape(len(pairs), -1)
        return [self.labels[k] for k in scores.argmax(axis=1)]


# ---------------------------------------------------------------------------
# Detector used by the pipeline
# ---------------------------------------------------------------------------


@dataclass
class UncertaintyResult:
    method: str
    entropy: float
    normalized_entropy: float
    flagged: bool
    num_samples: int
    samples: List[str] = field(default_factory=list)
    latency: Optional[float] = None


class KLEDetector:
    """
    Samples extra answers from an OpenAI-compatible client and scores them with KLE.

    `estimate()` is meant to run as a background task while the main answer streams.
    It never raises for expected failures (rate limits, timeouts). It returns None and
    logs instead, so a failed estimate never breaks the chat answer.
    """

    method = "kle-heat"

    def __init__(
        self,
        client: Any,
        model: str,
        nli: NLIModel,
        num_samples: int = 5,
        temperature: float = 1.0,
        heat_t: float = 1.0,
        threshold: float = 0.4,
        min_samples: int = 3,
        request_timeout: float = 30.0,
    ):
        if num_samples < 2:
            raise ValueError("KLE needs at least 2 samples")
        self.client = client
        self.model = model
        self.nli = nli
        self.num_samples = num_samples
        self.temperature = temperature
        self.heat_t = heat_t
        self.threshold = threshold
        self.min_samples = max(2, min(min_samples, num_samples))
        self.request_timeout = request_timeout

    async def sample(self, messages: List[dict]) -> List[str]:
        client = self.client.with_options(max_retries=1, timeout=self.request_timeout)

        async def one() -> str:
            completion = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                n=1,
            )
            return strip_reasoning(completion.choices[0].message.content or "")

        results = await asyncio.gather(
            *(one() for _ in range(self.num_samples)), return_exceptions=True
        )
        samples = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("KLE sample failed: %r", result)
            elif result:
                samples.append(result)
        return samples

    def score(self, samples: Sequence[str]) -> UncertaintyResult:
        weights = semantic_weights(samples, self.nli)
        entropy = kernel_language_entropy(weights, t=self.heat_t)
        normalized = entropy / max_entropy(len(samples))
        return UncertaintyResult(
            method=self.method,
            entropy=entropy,
            normalized_entropy=normalized,
            flagged=normalized >= self.threshold,
            num_samples=len(samples),
            samples=list(samples),
        )

    async def estimate(self, messages: List[dict]) -> Optional[UncertaintyResult]:
        start = time.time()
        try:
            samples = await self.sample(messages)
            if len(samples) < self.min_samples:
                logger.warning(
                    "KLE skipped: only %d of %d samples succeeded",
                    len(samples),
                    self.num_samples,
                )
                return None
            # NLI is CPU-bound; keep it off the event loop.
            result = await asyncio.to_thread(self.score, samples)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("KLE estimation failed")
            return None
        result.latency = time.time() - start
        logger.info(
            "KLE entropy=%.3f normalized=%.3f flagged=%s samples=%d latency=%.2fs",
            result.entropy,
            result.normalized_entropy,
            result.flagged,
            result.num_samples,
            result.latency,
        )
        return result
