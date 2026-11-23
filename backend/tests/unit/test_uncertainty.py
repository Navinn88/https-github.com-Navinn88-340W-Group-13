import asyncio
import math
from types import SimpleNamespace

import numpy as np
import pytest

from marcel.uncertainty import (
    CONTRADICTION,
    ENTAILMENT,
    NEUTRAL,
    KLEDetector,
    heat_kernel,
    kernel_language_entropy,
    normalize_kernel,
    semantic_weights,
    strip_reasoning,
    von_neumann_entropy,
)


def cluster_weights(sizes, within=2.0, across=0.0):
    n = sum(sizes)
    weights = np.full((n, n), across)
    start = 0
    for size in sizes:
        weights[start : start + size, start : start + size] = within
        start += size
    return weights


class FakeNLI:
    """Answers with the same first word entail each other, others contradict."""

    def __init__(self):
        self.calls = 0

    def predict(self, pairs):
        self.calls += len(pairs)
        return [
            ENTAILMENT if a.split()[0] == b.split()[0] else CONTRADICTION
            for a, b in pairs
        ]


def test_normalized_kernel_is_unit_trace_psd():
    kernel = normalize_kernel(heat_kernel(cluster_weights([3, 2]), t=1.0))
    assert np.trace(kernel) == pytest.approx(1.0)
    assert np.allclose(kernel, kernel.T)
    assert np.linalg.eigvalsh(kernel).min() > -1e-10


def test_von_neumann_entropy_of_maximally_mixed_state():
    n = 4
    assert von_neumann_entropy(np.eye(n) / n) == pytest.approx(math.log(n))


def test_kle_bounds():
    n = 5
    agree = kernel_language_entropy(cluster_weights([n]), t=1.0)
    disagree = kernel_language_entropy(cluster_weights([1] * n), t=1.0)
    assert agree == pytest.approx(0.0, abs=0.01)
    assert disagree == pytest.approx(math.log(n))


def test_kle_increases_with_semantic_diversity():
    values = [
        kernel_language_entropy(cluster_weights(sizes), t=1.0)
        for sizes in ([5], [4, 1], [3, 2], [2, 2, 1], [1, 1, 1, 1, 1])
    ]
    assert values == sorted(values)
    assert len(set(np.round(values, 6))) == len(values)


def test_neutral_is_between_entailment_and_contradiction():
    entail = kernel_language_entropy(np.full((5, 5), 2.0), t=1.0)
    neutral = kernel_language_entropy(np.full((5, 5), 1.0), t=1.0)
    contradict = kernel_language_entropy(np.zeros((5, 5)), t=1.0)
    assert entail < neutral < contradict


def test_single_answer_has_zero_entropy():
    assert kernel_language_entropy(np.zeros((1, 1))) == 0.0


def test_semantic_weights_symmetric_and_skips_identical():
    nli = FakeNLI()
    texts = ["Yes, you need a BSc.", "Yes, a bachelor.", "No, any degree works."]
    weights = semantic_weights(texts, nli)
    assert np.allclose(weights, weights.T)
    assert weights[0, 1] == 2.0  # entail both ways
    assert weights[0, 2] == 0.0  # contradict both ways
    assert nli.calls == 6

    nli = FakeNLI()
    semantic_weights(["same", "same", "other"], nli)
    assert nli.calls == 4  # the identical pair is not sent to the model


def test_semantic_weights_neutral():
    class NeutralNLI:
        def predict(self, pairs):
            return [NEUTRAL] * len(pairs)

    weights = semantic_weights(["a", "b"], NeutralNLI())
    assert weights[0, 1] == 1.0


def test_strip_reasoning():
    assert strip_reasoning("<think>hmm\nok</think>\nThe answer.") == "The answer."
    assert strip_reasoning(None) == ""


class FakeCompletions:
    def __init__(self, answers):
        self.answers = list(answers)
        self.kwargs = []

    async def create(self, **kwargs):
        self.kwargs.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        message = SimpleNamespace(content=answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, answers):
        self.chat = SimpleNamespace(completions=FakeCompletions(answers))

    def with_options(self, **kwargs):
        return self


def make_detector(answers, **kwargs):
    client = FakeClient(answers)
    detector = KLEDetector(
        client=client,
        model="test-model",
        nli=FakeNLI(),
        num_samples=len(answers),
        **kwargs,
    )
    return detector, client


def test_detector_low_uncertainty_for_consistent_answers():
    detector, client = make_detector(["Yes a"] * 5, threshold=0.4)
    result = asyncio.run(detector.estimate([{"role": "user", "content": "q"}]))
    assert result is not None
    assert result.num_samples == 5
    assert result.normalized_entropy < 0.05
    assert not result.flagged
    assert result.latency is not None
    kwargs = client.chat.completions.kwargs[0]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 1.0


def test_detector_flags_contradicting_answers():
    detector, _ = make_detector(["A x", "B x", "C x", "D x", "E x"], threshold=0.4)
    result = asyncio.run(detector.estimate([{"role": "user", "content": "q"}]))
    assert result.normalized_entropy == pytest.approx(1.0)
    assert result.flagged


def test_detector_tolerates_some_failed_samples():
    detector, _ = make_detector(["Yes a", RuntimeError("429"), "Yes b", "Yes c"])
    result = asyncio.run(detector.estimate([{"role": "user", "content": "q"}]))
    assert result is not None
    assert result.num_samples == 3


def test_detector_returns_none_when_too_few_samples():
    detector, _ = make_detector(
        ["Yes a", RuntimeError("429"), RuntimeError("429"), RuntimeError("429")]
    )
    result = asyncio.run(detector.estimate([{"role": "user", "content": "q"}]))
    assert result is None


def test_detector_returns_none_when_nli_fails():
    class BrokenNLI:
        def predict(self, pairs):
            raise RuntimeError("model not loaded")

    detector, _ = make_detector(["A x", "B x", "C x"])
    detector.nli = BrokenNLI()
    assert asyncio.run(detector.estimate([])) is None


def test_detector_requires_two_samples():
    with pytest.raises(ValueError):
        KLEDetector(client=None, model="m", nli=FakeNLI(), num_samples=1)
