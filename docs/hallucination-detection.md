# Hallucination detection (Kernel Language Entropy)

CIRA can flag answers that are likely to be hallucinated, using Kernel Language
Entropy (KLE) from [Nikitin et al., NeurIPS 2024](https://arxiv.org/abs/2405.20003).

## How it works

If a model knows the answer, answers sampled independently for the same question mean the
same thing. If it is guessing, they disagree. For every question that goes through
retrieval, CIRA:

1. Generates `KLE_NUM_SAMPLES` extra answers to the same prompt (same documents and
   history) at `KLE_TEMPERATURE`. This runs in the background while the main answer streams.
2. Runs an NLI model (`KLE_NLI_MODEL`) on every pair of sampled answers. The edge weight
   between two answers is f(a→b) + f(b→a), with f = 1 for entailment, 0.5 for neutral
   and 0 for contradiction.
3. Builds the graph Laplacian L, the heat kernel exp(−t·L) with t = `KLE_HEAT_T`, and
   normalises it to unit trace.
4. Takes its von Neumann entropy. It is divided by log(N) to get a score between 0
   (all answers agree) and 1 (all answers contradict each other).

If the score is at least `KLE_THRESHOLD`, the answer is flagged. Users then see a warning
under the answer. Answers where CIRA says it has no information are never flagged.
Admins see the score and all sampled answers in the conversation view.

The code is in `backend/src/marcel/uncertainty.py`. Scores are stored in the
`uncertainty_estimate` table. This new table is created automatically on startup, so no
migration is needed.

## Enabling it

Set these in `.env`, then rebuild and restart:

```sh
KLE_ENABLED=true
```

```sh
docker compose build backend
docker compose --env-file .env up -d
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `KLE_ENABLED` | `false` | Turn detection on |
| `KLE_NUM_SAMPLES` | `5` | Extra answers per question (the paper uses 10) |
| `KLE_TEMPERATURE` | `1.0` | Sampling temperature for the extra answers |
| `KLE_HEAT_T` | `1.0` | Heat kernel time t (the paper's default is 0.3, see below) |
| `KLE_THRESHOLD` | `0.4` | Flag answers with a normalised score at or above this |
| `KLE_NLI_MODEL` | `cross-encoder/nli-deberta-v3-small` | NLI model (changing it requires a rebuild) |
| `KLE_SAMPLE_MODEL` | `MODEL_NAME` | Model for the extra samples, e.g. a cheaper one |
| `KLE_TIMEOUT` | `45` | Seconds to wait for the score after the answer has streamed |

## Costs and limits

- **LLM calls:** each question costs 1 + `KLE_NUM_SAMPLES` generations. Free API tiers
  have low per-minute token limits. If samples fail (for example with HTTP 429), the
  score is computed from the ones that succeeded (at least 3). If fewer succeed, no score
  is computed and the answer is shown without one. The answer itself is never affected.
- **Latency:** sampling runs in parallel with the main answer. The NLI step adds well
  under a second on CPU for 5 samples (20 pairs). Users may see the warning appear just
  after the answer finishes.
- **Memory:** the NLI model is loaded once per uvicorn worker (`UVICORN_WORKERS`, 4 by
  default in `docker-compose.yaml`).

## Choosing `KLE_HEAT_T` and `KLE_THRESHOLD`

Normalised scores for 5 answers in some typical patterns:

| Answers | t = 0.3 | t = 1.0 |
| --- | --- | --- |
| all agree | 0.42 | 0.00 |
| all "neutral" to each other | 0.84 | 0.10 |
| 4 agree, 1 contradicts | 0.69 | 0.32 |
| 3 vs 2 contradicting groups | 0.83 | 0.45 |
| 2 + 2 + 1 groups | 0.92 | 0.70 |
| all contradict | 1.00 | 1.00 |

CIRA's answers are long paragraphs, and NLI often rates two consistent but differently
worded paragraphs as "neutral". With t = 0.3, that looks almost as uncertain as real
contradictions. t = 1.0 keeps them apart, which is why it is the default here.

These defaults come from synthetic patterns, not real data. To calibrate them, compare
`uncertainty_estimate.normalized_entropy` with answers you have judged correct or wrong
(for example the thumbs-down feedback in `message.feedback`). Then pick the threshold that
best separates them.
