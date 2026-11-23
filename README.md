# CIRA: Canvas Information Retrieval Assistant

CIRA is a Retrieval Augmented Generation (RAG) LLM Canvas assistant with self-evaluation and entropy-based hallucination detection. It helps students find relevant course information and presents it in a consistent, interpretable style that suits the individual. It is designed to run in a university environment with limited resources compared with a large technology company, while still producing accurate and relevant responses. The goal is to make course and assignment information easier to reach and to cut the time students spend on simple navigation and troubleshooting.

Our rationale is that an interactive assistant can adapt to the situational needs of the student, which is beyond the capabilities of the Canvas application.

CIRA is built on [Marcel](https://github.com/aix-group/marcel-chat), an open-source university chatbot (see [Credits](#credits)).

## Features

- **Answers grounded in course material.** CIRA retrieves passages from a knowledge base (course PDFs, slides, documents and a Penn State Canvas FAQ) and answers only from them. If the answer isn't there, it says so instead of guessing.
- **FAQ retriever.** Frequently asked questions are mapped to the documents that answer them, so common questions reliably find the right source.
- **Hallucination detection with Kernel Language Entropy (KLE).** For every question, CIRA generates several extra answers in the background and checks whether they agree with each other. If they disagree, the answer gets a warning asking the student to double-check it. Based on [Nikitin et al., NeurIPS 2024](https://arxiv.org/abs/2405.20003).
- **Source attribution.** Each answer links to the documents it was based on ("Where can I verify this answer?").
- **Feedback.** Students can rate answers (thumbs up/down) and whole conversations.
- **Admin interface.** Usage statistics, a list of conversations, and the hallucination score and sampled answers for every response.

## Quickstart

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and an API key for an OpenAI-compatible LLM provider. We use [Groq](https://console.groq.com/keys), which has a free tier.

### 1. Clone the repository

```sh
git clone https://github.com/Navinn88/https-github.com-Navinn88-340W-Group-13.git
cd https-github.com-Navinn88-340W-Group-13
```

### 2. Create the `.env` file

Create a file called `.env` in the project root (next to `docker-compose.yaml`) with the following content, and fill in the values marked `<...>`:

```sh
# --- Data (paths inside the Docker container) ---
DATA_ROOT=/data
DATA_PATH=knowledgebase.jsonl
FAQ_PATH=faq.json
ADMINS_PATH=admins.json

# --- Admin login ---
# Generate a secret with: openssl rand -hex 32
SECRET_KEY=<64 random hex characters>
ACCESS_TOKEN_EXPIRE_MINUTES=60

# --- LLM (any OpenAI-compatible API; Groq shown here) ---
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=<your Groq key, starts with gsk_>
MODEL_NAME=openai/gpt-oss-120b

# --- Database (MariaDB, runs in Docker) ---
MARIADB_DATABASE=marcel
MARIADB_USER=marcel
MARIADB_PASSWORD=<choose a password>
MARIADB_ROOT_PASSWORD=<choose another password>
DATABASE_URI=mysql://${MARIADB_USER}:${MARIADB_PASSWORD}@database:3306/${MARIADB_DATABASE}

# --- Hallucination detection (KLE) ---
KLE_ENABLED=true
KLE_NUM_SAMPLES=3
KLE_SAMPLE_MODEL=openai/gpt-oss-20b
KLE_TEMPERATURE=1.0
KLE_HEAT_T=1.0
KLE_THRESHOLD=0.4
KLE_NLI_MODEL=cross-encoder/nli-deberta-v3-small
KLE_TIMEOUT=45
```

Never commit `.env`: it contains your API key and passwords. It is already listed in `.gitignore`.

All `KLE_` settings are explained in [Hallucination detection settings](#hallucination-detection-settings).

### 3. Generate certificates

CIRA is served over HTTPS. For local development, create a self-signed certificate:

```sh
mkdir certs
cd certs
openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout selfsigned.key \
  -out  selfsigned.crt \
  -subj "/CN=localhost"
cd ..
```

On Windows (Git Bash), write `-subj "//CN=localhost"` with two slashes.

### 4. Build and start

```sh
docker compose build
docker compose --env-file .env up -d
```

The first build takes several minutes because it downloads the embedding model and the NLI model used for hallucination detection. After starting, the backend needs about a minute to load its models. Check progress with:

```sh
docker compose ps
```

When `backend` shows `(healthy)`, open **https://localhost:8080/**. Your browser will warn about the self-signed certificate; continue anyway.

To stop everything:

```sh
docker compose down
```

### Troubleshooting

- **`502 Bad Gateway` after rebuilding:** the `nginx` container still points at the old containers. Run `docker compose restart nginx`, or restart everything with `docker compose down` followed by `docker compose --env-file .env up -d`.
- **`exec /app/scripts/entrypoint.sh: no such file or directory` on Windows:** the shell scripts were checked out with Windows line endings. The repository's `.gitattributes` prevents this for new clones. For an existing clone, delete `backend/scripts/*.sh`, run `git checkout -- backend/scripts`, and rebuild.
- **`Invalid API key` or `model … does not exist`:** check `LLM_BASE_URL`, `LLM_API_KEY` and `MODEL_NAME` in `.env`. Providers retire models from time to time, so check their current model list.
- **Changed `.env`?** Restart with `docker compose down` and `docker compose --env-file .env up -d`. Changing `KLE_NLI_MODEL` also needs `docker compose build backend`.
- **See what the backend is doing:** `docker compose logs -f backend`

## Hallucination detection settings

When a question is answered from the knowledge base, CIRA generates `KLE_NUM_SAMPLES` extra answers to the same prompt. An NLI model then checks every pair for entailment or contradiction, and Kernel Language Entropy turns that into a score from 0 (all answers agree) to 1 (all answers contradict each other). Answers scoring at or above `KLE_THRESHOLD` get a warning. Answers where CIRA says it has no information are never flagged.

| Variable | Default | Recommended (Groq free tier) | What it does |
| --- | --- | --- | --- |
| `KLE_ENABLED` | `false` | `true` | Turns hallucination detection on |
| `KLE_NUM_SAMPLES` | `5` | `3` | Extra answers per question. More gives a more reliable score but uses more API tokens. |
| `KLE_SAMPLE_MODEL` | same as `MODEL_NAME` | `openai/gpt-oss-20b` | Model for the extra answers. A different model from `MODEL_NAME` gets its own rate limit on Groq. |
| `KLE_TEMPERATURE` | `1.0` | `1.0` | Sampling temperature for the extra answers. It must be high enough for an uncertain model to vary. |
| `KLE_HEAT_T` | `1.0` | `1.0` | Heat kernel parameter. The paper uses 0.3 for short answers; 1.0 works better for CIRA's longer answers. |
| `KLE_THRESHOLD` | `0.4` | `0.4` | Score (0 to 1) at or above which an answer is flagged |
| `KLE_NLI_MODEL` | `cross-encoder/nli-deberta-v3-small` | default | NLI model that compares the answers. Changing it requires a rebuild. |
| `KLE_TIMEOUT` | `45` | `45` | Seconds to wait for the score after the answer finishes |

**Checking scores:**

- `docker compose logs backend | grep "KLE entropy"` shows one line per scored answer, for example `KLE entropy=0.412 normalized=0.256 flagged=False samples=3`.
- In the admin interface, every answer shows its score and the sampled answers, so you can see where they disagreed.

**Limits on the Groq free tier:** each extra answer resends the question and the retrieved documents, roughly 2,000 to 4,500 tokens. Groq's free tier allows 8,000 tokens per minute per model, shared across your whole organization. When the limit is hit, failed samples are logged as `KLE sample failed` (HTTP 429), and the question is skipped (`KLE skipped`) if fewer than 3 samples succeed. The answer itself is never affected. Keep `KLE_NUM_SAMPLES=3`, use a separate `KLE_SAMPLE_MODEL`, and leave about a minute between test questions.

**Calibrating the threshold:** the default of 0.4 is a starting point, not a tested value. To check that the warning works end to end, set `KLE_THRESHOLD=0.05` temporarily. To calibrate, compare scores with answers you know are right or wrong, and pick the value that best separates them.

More detail on how it works and the code involved: [docs/hallucination-detection.md](./docs/hallucination-detection.md).

## Data

All data lives in the [`data`](./data/) folder. After changing it, restart the containers; new documents are loaded automatically on startup.

### Knowledge base (`knowledgebase.jsonl`)

The documents CIRA answers from. One JSON object per line, with the keys `url`, `content`, `favicon` and `og` (Open Graph metadata such as `og:title`, which is shown as the source title; it can be an empty object `{}`).

<details>
<summary><b>Example entry</b></summary>

```json
{
    "url": "https://github.com/Navinn88/https-github.com-Navinn88-340W-Group-13/blob/main/docs/canvas-faq.md",
    "content": "# Penn State Canvas FAQ\n\n## Getting Started & Access\n\n**Q: How do I log in to Penn State Canvas?**\nA: Go to psu.instructure.com and sign in ...",
    "og": {
        "og:title": "Penn State Canvas FAQ",
        "og:type": "website",
        "og:url": "https://github.com/Navinn88/https-github.com-Navinn88-340W-Group-13/blob/main/docs/canvas-faq.md"
    },
    "favicon": "https://github.githubassets.com/favicons/favicon.png"
}
```

</details>

### FAQ (`faq.json`)

Questions that should reliably lead to a specific document. Each entry has an `id`, the `question`, and `sources`, a list of knowledge base URLs that answer it. The current FAQ covers Penn State Canvas and points to [`docs/canvas-faq.md`](./docs/canvas-faq.md).

- Every URL in `sources` must exactly match a `url` in the knowledge base, or the FAQ entry is ignored (the backend logs `No parent for faq`).
- Anything after `#` in a URL is ignored when matching, so an FAQ can point to a whole PDF but not to a single page of it.

<details>
<summary><b>Example entry</b></summary>

```json
[
    {
        "id": "faq-0000",
        "question": "How do I log in to Penn State Canvas?",
        "sources": [
            "https://github.com/Navinn88/https-github.com-Navinn88-340W-Group-13/blob/main/docs/canvas-faq.md"
        ]
    }
]
```

</details>

### Admin users (`admins.json`)

Accounts for the admin interface at https://localhost:8080/admin/login. Passwords are stored as Argon2 hashes; see the [backend instructions](./backend/README.md) for how to create one.

<details>
<summary><b>Example entry</b></summary>

```json
[
    {
        "username": "admin",
        "hashed_password": "$argon2id$v=19$m=65536,t=3,p=4$..."
    }
]
```

</details>

## Admin interface

Sign in at **https://localhost:8080/admin/login**.

- **Home:** usage statistics over a selectable time period.
- **Conversations:** every conversation, with each answer's sources, feedback, hallucination score and sampled answers.

## Development

- [Backend](./backend/README.md)
- [Frontend](./frontend/README.md)
- [Scraper](./scraper/README.md)
- [Docker deployment](./docs/docker.md)
- [Hallucination detection (KLE)](./docs/hallucination-detection.md)

## Credits

CIRA is built on **Marcel**, developed at the University of Marburg and released under the MIT license ([repository](https://github.com/aix-group/marcel-chat), [paper](https://aclanthology.org/2025.emnlp-demos.13/)). If you use this work, please also cite the original paper:

```bibtex
@inproceedings{trienes-etal-2025-marcel,
    title = "Marcel: A Lightweight and Open-Source Conversational Agent for University Student Support",
    author = {Trienes, Jan  and
      Derzhanskaia, Anastasiia  and
      Schwarzkopf, Roland  and
      M{\"u}hling, Markus  and
      Schl{\"o}tterer, J{\"o}rg  and
      Seifert, Christin},
    booktitle = "Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: System Demonstrations",
    month = nov,
    year = "2025",
    address = "Suzhou, China",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2025.emnlp-demos.13/",
    doi = "10.18653/v1/2025.emnlp-demos.13",
    pages = "181--195"
}
```

Hallucination detection follows:

```bibtex
@inproceedings{nikitin2024kernel,
    title = "Kernel Language Entropy: Fine-grained Uncertainty Quantification for LLMs from Semantic Similarities",
    author = "Nikitin, Alexander and Kossen, Jannik and Gal, Yarin and Marttinen, Pekka",
    booktitle = "Advances in Neural Information Processing Systems",
    year = "2024",
    url = "https://arxiv.org/abs/2405.20003"
}
```
