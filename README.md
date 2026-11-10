# AI Powered University Chatbot

**Project:** 351 CP 81 Comprehension, Project 2
**Student:** Asante Mbaya
**Institution:** DMI St. John the Baptist University
**Scope:** A Django REST API backend (sections 1–16) and a React web interface, "Campus Desk" (section 17).

> **Important: demonstration data.** The knowledge base that ships with this project is
> **hypothetical demonstration data** written for an academic prototype. It has **not** been
> verified with DMI St. John the Baptist University. No real fees, dates, phone numbers or
> e-mail addresses are included. The backend labels every such answer as demonstration
> information, and it can be switched into an *official mode* that uses only verified records.

---

## Contents

1. [Overview](#1-overview)
2. [Problem statement and objectives](#2-problem-statement-and-objectives)
3. [Scope](#3-scope)
4. [System architecture](#4-system-architecture)
5. [Technology stack](#5-technology-stack)
6. [The machine learning model](#6-the-machine-learning-model)
7. [The NLP pipeline](#7-the-nlp-pipeline)
8. [Database structure](#8-database-structure)
9. [Dataset](#9-dataset)
10. [Installation](#10-installation)
11. [Running the application](#11-running-the-application)
12. [API documentation](#12-api-documentation)
13. [Testing](#13-testing)
14. [Performance on the development laptop](#14-performance-on-the-development-laptop)
15. [Known limitations](#15-known-limitations)
16. [Future improvements](#16-future-improvements)
17. [Web interface (Campus Desk)](#17-web-interface-campus-desk)

---

## 1. Overview

The chatbot answers frequently asked questions about university programmes, admissions, fees
and academic services. A user types a question in ordinary language. The backend:

1. works out what the question *means* using a pre-trained Sentence Transformer
   (`sentence-transformers/all-MiniLM-L6-v2`), running locally on the CPU;
2. finds the most similar question stored in a PostgreSQL knowledge base;
3. returns the stored, human-written answer, or an honest fallback message if nothing
   relevant is found.

The chatbot is **retrieval based**. It never generates facts. Every answer is an exact record
from the knowledge base, together with its source and its verification status.

## 2. Problem statement and objectives

University information is spread across prospectuses, notice boards, websites and offices.
Prospective and current students struggle to find simple answers, such as how to apply, how
fees are paid or where to find the academic calendar. Staff answer the same questions
repeatedly.

**Objectives**

* Provide a single, centralised and administrable university knowledge base.
* Let users ask questions in natural language, matched by **meaning** rather than exact
  wording.
* Never invent answers: return verified (or clearly labelled demonstration) information only.
* Support guests and registered users, keep conversation history, and collect feedback.
* Give administrators analytics on usage, performance and unanswered questions (knowledge gaps).
* Expose everything through a documented REST API for a future frontend.

## 3. Scope

**Included:** Django backend, PostgreSQL database, local NLP model integration, dataset and
importer, chatbot pipeline, conversation management, authentication and roles, feedback,
analytics, Django Admin for knowledge management, OpenAPI/Swagger documentation and automated
tests.

**Excluded (by design):** any user-facing frontend (web pages, chat UI, CSS, JavaScript,
React and so on). The frontend will be developed separately against this API. Django Admin is
used only as a backend management tool.

## 4. System architecture

```
 Frontend (future, separate) ──HTTP/JSON──►  Django REST Framework API  (/api/...)
                                              │
        ┌──────────────┬──────────────────────┼──────────────────┬───────────────┐
        ▼              ▼                      ▼                  ▼               ▼
   accounts         chat                knowledge_base       feedback        analytics
 (users, roles,  (conversations,      (categories, FAQs,    (ratings of     (query log,
  token auth)    messages, pipeline    alternatives,         responses)      statistics,
                  orchestration)       articles, importer,                   knowledge gaps)
                       │               embedding sync,
                       │               search index)
                       ▼                      │
                  nlp_engine  ◄───────────────┘
   (model_loader, preprocessing, embeddings, intent_classifier,
    semantic_search, response_generator): pure Python, no database access
                       │
                       ▼
     all-MiniLM-L6-v2 (local files in ./ml_models, CPU)       PostgreSQL (source of truth)
```

| App / package    | Responsibility |
|------------------|----------------|
| `config`         | Settings (all values from environment variables), URL routing, WSGI/ASGI. |
| `core`           | Shared base model, pagination, safe error handler, health endpoint, test helpers. |
| `accounts`       | Custom `User` with roles, registration, login/logout (tokens), profile, password change, admin user management. |
| `nlp_engine`     | Model loading (once per process), preprocessing, embeddings, intent detection, cosine-similarity search, threshold and clarification decisions, grounded response generation. Independent of the database. |
| `knowledge_base` | Knowledge models, dataset importer, embedding persistence and automatic refresh (signals), in-memory search index, knowledge API and Django Admin. |
| `chat`           | Conversations and messages, guest sessions, the chatbot pipeline service (`chat/services.py`), conversational context. |
| `feedback`       | Ratings and comments on chatbot responses. |
| `analytics`      | One analytics record per question; statistics computed from stored data; unanswered-question review. |

Business logic lives in `services.py` modules. Views only validate requests and format
responses, and logic is not duplicated between apps.

## 5. Technology stack

| Purpose | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | Django 5.2 |
| REST API | Django REST Framework 3.16+ |
| Database | PostgreSQL (tested with PostgreSQL 18), psycopg 3 with connection pooling |
| ML model | `sentence-transformers/all-MiniLM-L6-v2`, run locally on the CPU with ONNX Runtime + Hugging Face `tokenizers` (default), or with the `sentence-transformers` library on PyTorch (optional) |
| Similarity | NumPy cosine similarity (equivalent to scikit-learn's `cosine_similarity`, checked in the tests) |
| Data processing | NumPy |
| Configuration | python-dotenv (`.env`) |
| API documentation | drf-spectacular (OpenAPI 3, Swagger UI, ReDoc) |
| Authentication | Django auth with DRF token authentication (plus session authentication for the browsable API) |
| CORS | django-cors-headers |
| Tests | Django `TestCase` / DRF `APITestCase` |

No paid or external AI service is used. The only network access is the **one-time** model
download.

## 6. The machine learning model

### 6.1 Sentence Transformers and sentence embeddings

A *sentence embedding* is a list of numbers (a vector) that represents the meaning of a
sentence. Sentences with similar meanings get vectors that point in similar directions, even
when they share no words. For example:

* "What programmes does the university offer?"
* "Which courses can I study here?"

**Sentence Transformers** are neural networks (based on the Transformer architecture used by
BERT) that were trained on very large collections of sentence pairs to produce such
embeddings.

This project uses **all-MiniLM-L6-v2**, a small, fast, pre-trained Sentence Transformer:

* 6 Transformer layers and about 22 million parameters (around 90 MB on disk);
* 384-dimensional output vectors;
* trained on over one billion sentence pairs;
* designed for semantic search and runs well on an ordinary CPU.

The model is **used as-is**. No model is trained in this project. Its role is to *understand*
questions. The *facts* come from the PostgreSQL knowledge base. The two are deliberately
separate: the model can be swapped without touching the data, and the data can be edited
without retraining anything.

### 6.2 Local execution

* `nlp_engine/model_loader.py` loads the model **once per server process** (thread-safe lazy
  singleton) from `./ml_models`. The server also preloads it in a background thread at start-up
  (`NLP_PRELOAD_MODEL=true`), so the first user does not wait.
* With `NLP_OFFLINE=true` the model is loaded with `local_files_only=True` and the Hugging
  Face Hub is never contacted.
* If the model files are missing, the API returns **HTTP 503** with installation
  instructions. It never silently falls back to an external service.
* Inference runs on the CPU with a small number of threads (automatically `min(4, cores/2)`,
  configurable with `NLP_THREADS`).

**Two runtimes for the same model (`NLP_BACKEND`).** The model's official Hugging Face
repository publishes an ONNX export (`onnx/model.onnx`) of the same weights.

* `onnx` (default): `nlp_engine/onnx_encoder.py` runs that export with ONNX Runtime and
  reproduces the Sentence Transformer pipeline for this model: tokenise (up to 256 tokens),
  Transformer, mean pooling over real tokens, L2 normalisation. Its embeddings are
  **numerically identical** to the PyTorch version: cosine similarity 1.000000 on all 258 stored
  knowledge base texts, maximum difference 2×10⁻⁷. An automated test checks this.
* `torch`: the `sentence-transformers` library on PyTorch (install `requirements-torch.txt`).

ONNX is the default because it makes the server about 9× faster to start, and far faster after
a reboot. Importing PyTorch and Transformers means loading over 4,000 Python files, which on
Windows (with antivirus scanning) took up to 2.5 minutes on a cold start. The ONNX runtime loads
about 790 files and is ready in about 1 second. See section 14.

### 6.3 Cosine similarity

The similarity between a question vector **q** and a stored vector **s** is

```
cos(q, s) = (q · s) / (‖q‖ · ‖s‖)
```

It ranges from −1 to 1 and measures the angle between the vectors, not their length. Values
near 1 mean very similar meaning. Values near 0 mean unrelated. The project computes it with
NumPy (`nlp_engine/similarity.py`), which gives the same result as scikit-learn's
`cosine_similarity` without loading scikit-learn and SciPy at start-up. The vectors are also
L2-normalised when stored.

Cosine scores are **not probabilities**. A score of 0.6 does not mean "60% sure". That is why
the answer threshold was chosen by measurement (see 7.4) and not assumed.

### 6.4 Embedding storage and reuse

* Embeddings are generated for every FAQ main question, every alternative formulation and
  every knowledge article. They are stored in PostgreSQL `JSONField`s, together with a SHA-256
  fingerprint of the text and the model name.
* When a record is saved (through Django Admin, the REST API or the importer), a signal
  re-encodes **only** the texts whose fingerprint changed. Saving an FAQ whose question did not
  change performs no model inference.
* For search, the stored vectors of all *retrievable* records are loaded into an in-memory
  NumPy matrix. The matrix is rebuilt automatically when the knowledge base changes (record
  count, last-modified time and an invalidation counter are checked). Archived, unpublished or
  deleted records therefore disappear from search immediately.
* Recently encoded question texts are kept in an in-process cache (up to 5,000 entries,
  about 7.5 MB), so a repeated question costs no inference at all.
* If the model was unavailable when a record was saved, the missing embedding is generated
  automatically the next time the index is built.

## 7. The NLP pipeline

Implemented in `chat/services.py` using the `nlp_engine` components:

```
question ─► 1 validate & preprocess ─► 2 embed (MiniLM, 384-d) ─► 3 detect intent
        ─► 4 cosine-similarity search over stored embeddings ─► 5 rank (best per FAQ)
        ─► 6 threshold + ambiguity decision ─► 7 conversational context (follow-ups only)
        ─► 8 grounded response (answer | clarification | fallback) ─► 9 save messages + analytics
```

### 7.1 Preprocessing (`nlp_engine/preprocessing.py`)

The input is rejected if it is empty, whitespace only, longer than 500 characters
(configurable), or has no letters or digits. Otherwise the text is cleaned *gently*: Unicode
normalisation (NFKC), curly quotes and dashes converted to plain characters, control characters
removed, repeated punctuation collapsed ("???" becomes "?"), and whitespace collapsed. **No
words are removed or stemmed**, because the Transformer relies on the full sentence. The
original text is kept for the conversation history.

### 7.2 Intent detection (`nlp_engine/intent_classifier.py`, `data/intents.json`)

Twelve intents are supported (Admissions, Programme, Fees, Registration, Examination, Academic
Calendar, Student Services, Library, Accommodation, Contact Information, General University,
Unknown). Each intent has 5–8 example phrases in `data/intents.json`. These are embedded once
with the same model. A question takes the intent of its most similar example phrase. If no
example reaches `NLP_INTENT_THRESHOLD` (0.40), the intent is `unknown`. No separate classifier
is trained, and the examples can be improved without changing code.

The detected intent is stored for analytics and is also used as a **tie-breaker**: when two
FAQs score almost equally, an FAQ whose category matches the detected intent is preferred.

### 7.3 Semantic retrieval (`nlp_engine/semantic_search.py`, `knowledge_base/services.py`)

The question vector is compared with every stored question and alternative-question vector.
Each FAQ is scored by its **best-matching formulation**, and the top results are ranked. Because
alternative formulations ("What grades do I need?", "What qualifications are required?") point
to the same FAQ, differently worded questions retrieve the same answer.

### 7.4 Similarity threshold and clarification

| Rule | Setting | Value |
|---|---|---|
| Best score below the threshold → fallback, nothing is invented | `CHATBOT_SIMILARITY_THRESHOLD` | **0.50** (initial experimental value 0.45) |
| Best score at or above this → answer directly | `CHATBOT_HIGH_CONFIDENCE` | 0.75 |
| Otherwise, if another FAQ is within this margin → ask the user to clarify (unless the intent tie-breaker resolves it) | `CHATBOT_CLARIFICATION_MARGIN` | 0.03 |

**How the threshold was chosen.** `python manage.py evaluate_retrieval` evaluates 55 held-out
paraphrases (questions that are *not* in the dataset) and 20 out-of-scope questions
(`data/evaluation_questions.json`). Results on the development laptop:

```
Top-1 retrieval accuracy (no threshold): 51/55 = 92.7%
Top-3 retrieval accuracy (no threshold): 54/55 = 98.2%
Best-match score, in-scope:     mean 0.755, min 0.357
Best-match score, out-of-scope: mean 0.250, max 0.498

threshold | correct wrong clarify fallback | rejected leaked | overall
     0.40 |      50     3       1        1 |       19      1 |   92.0%
     0.45 |      50     3       1        1 |       19      1 |   92.0%
     0.50 |      50     3       1        1 |       20      0 |   93.3%
     0.55 |      49     3       0        3 |       20      0 |   92.0%
     0.60 |      49     1       1        4 |       20      0 |   92.0%
```

At 0.45, one out-of-scope question ("What time is it in New York?", score 0.498) was answered
with office hours. At **0.50**, all 20 out-of-scope questions are rejected and 50 of 55
paraphrases are answered correctly, so 0.50 was adopted. The remaining errors are listed by
`--verbose-errors`. They are mostly near-neighbour FAQs (for example "pay fees bit by bit"
retrieves *payment methods* instead of *instalments*). These are dataset gaps to be fixed by
adding alternative formulations, not by lowering the threshold.

### 7.5 Conversational context

Short follow-ups such as "What about the fees?" or "How much does it cost?" are detected with
simple rules (an opening phrase like "what about…", or a short message containing a pronoun).
For these messages only, the question embedding is **blended** with a smaller share (0.35) of
the previous answered question's embedding:

```
v = normalise( v_followup + 0.35 · v_previous_topic )
```

The new wording stays dominant while the topic is resolved. For example, "How much does it
cost?" after a hostel question retrieves *hostel accommodation cost*, not *tuition fees*. The
previously answered FAQ is excluded, and the result must still pass the same threshold. Context
is used only when it improves on the question alone, so it **can never override the knowledge
base or introduce new content**.

### 7.6 Response generation and labelling (`nlp_engine/response_generator.py`)

* **answer**: the stored answer text, plus its source. If the record is not verified
  institutional information, a label and disclaimer are appended, for example
  `[Demonstration information] This is hypothetical demonstration information …`, and the
  response carries `information_type`, `verification_status`, `is_verified` and `disclaimer`
  fields.
* **clarification**: "Your question could relate to more than one topic. Did you mean …?",
  with `suggestions`.
* **fallback**: "I'm sorry, I couldn't find verified information about that question in the
  university knowledge base. Please contact the relevant university department for
  assistance." The question is logged as *unanswered* for administrator review.
* **small_talk**: fixed greeting, thanks and goodbye replies (not counted as answered
  questions).

The `ResponseGenerator` class is the single place where an optional LLM paraphrasing step could
be added in future. Any such step would have to keep the retrieved facts unchanged.

### 7.7 Demo mode and official mode (enforced in the backend)

| Record | `CHATBOT_DEMO_MODE=true` | `CHATBOT_DEMO_MODE=false` (official) |
|---|---|---|
| published + verified + institutional | used, no disclaimer | used |
| published + unverified (demonstration) | used, **labelled** | **never used** |
| draft (verification or publication) / archived | never used | never used |

The rule is a single database filter (`knowledge_base.models.retrievable_filter`) used by the
search index, the public knowledge API and the chatbot. The model validation also forbids
marking *demonstration* information as *verified*. An administrator must first change it to
institutional information after confirming the facts.

## 8. Database structure

| Model | Key fields | Notes |
|---|---|---|
| `accounts.User` | id, username, email (unique), password (hashed), first/last name, `role` (administrator, student, prospective_student, guest), `is_active` (account status), `date_joined`, `last_login` | Extends Django's `AbstractUser`. Superusers are always administrators. |
| `knowledge_base.KnowledgeCategory` | id, name, slug, description, `intent`, created_at, updated_at | 12 categories |
| `knowledge_base.FAQ` | id, `reference_code` (e.g. ADM-002), question, answer, category → Category, keywords (JSON list), source_description, source_url, `verification_status`, `publication_status`, `information_type`, `question_embedding` (JSON, 384 floats), embedding_hash, created_at, updated_at | Composite index on the three status fields |
| `knowledge_base.AlternativeQuestion` | id, faq → FAQ (cascade), question_text, embedding, embedding_hash, created_at, updated_at | Unique per (faq, text) |
| `knowledge_base.KnowledgeArticle` | id, reference_code, title, content, category, source_description (exposed as `source`), source_url, statuses, embedding | Searchable through `/api/knowledge/search/` |
| `chat.Conversation` | id, user → User (nullable), `guest_session_id` (SHA-256 of the guest token), title, status (active/archived), created_at, updated_at | Check constraint: a conversation must have a user or a guest session |
| `chat.Message` | id, conversation → Conversation, sender_type (user/bot), content, detected_intent, intent_confidence, similarity_score, retrieved_faq → FAQ, response_type, answered, information_type, metadata (sources, disclaimer, top candidates), created_at | Index on (conversation, created_at) |
| `feedback.ChatbotFeedback` | id, message → Message (one-to-one), user, rating (1–5), comment, created_at | Positive ≥ 4, negative ≤ 2 |
| `analytics.QueryAnalytics` | id, original_question, normalized_question, conversation, message, detected_intent, retrieved_faq, category, similarity_score, answered, response_type, used_context, response_time_ms, review_status (pending/resolved/dismissed), resolved_faq, admin_notes, timestamp | One row per question |

All database access goes through the Django ORM (parameterised queries, so there is no SQL
injection). Embeddings are stored as JSON for simplicity. `pgvector` is an optional future
optimisation (see section 16).

## 9. Dataset

* **File:** `data/university_faqs.json` (12 categories, **57 FAQs**, **201 alternative
  formulations**, 3 knowledge articles).
* **Categories:** University General Information, Academic Programmes, Admissions, Tuition and
  Fees, Student Registration, Examinations, Academic Calendar, Student Affairs, Library
  Services, Accommodation, Student Support, University Contact Information.
* **Record fields:** `reference_code`, `category`, `question`, `answer`,
  `alternative_questions`, `keywords`, `source_description`, `source_url`,
  `verification_status`, `publication_status`, `information_type`. Shared values are defined
  once in `metadata.defaults`. FAQ ID, created and updated dates are assigned by the database.
* **Labelling:** every record is `information_type: demonstration`,
  `verification_status: unverified`. Answers are written cautiously ("In this demonstration
  scenario…", "As a hypothetical example…") and point to the responsible office. Where a
  general public fact about Malawi is mentioned (for example the National Council for Higher
  Education, or the Higher Education Students' Loans and Grants Board), the user is still told
  to verify the details.
* **Supporting files:** `data/intents.json` (intent example phrases) and
  `data/evaluation_questions.json` (held-out evaluation set).

**Import** (`python manage.py import_faqs [path] [--skip-embeddings]`):

1. validates every record (required fields, valid statuses, known categories, URL format,
   duplicate codes or questions, and demonstration information marked as verified). If any
   record is invalid, nothing is imported and every error is listed;
2. creates or updates categories;
3. creates or updates FAQs and articles, matched on `reference_code`;
4. synchronises alternative formulations to exactly the list in the file;
5. generates the missing or changed embeddings in one batch;
6. prints a summary.

Running it again creates **no duplicates**. On a second run it reports "57 unchanged" and
generates 0 embeddings.

## 10. Installation

Tested on Windows 11 with Python 3.12 and PostgreSQL 18. The same steps work on Linux and
macOS (use `source .venv/bin/activate`).

### 10.1 Python environment

```powershell
cd "D:\Projects\AI Powered University Chatbot"
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs the default ONNX runtime, with no PyTorch needed. To also use the optional PyTorch
backend (and run the test proving both backends give identical embeddings):

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-torch.txt
```

> Python 3.12 is recommended.

### 10.2 PostgreSQL

**Option A: your existing PostgreSQL service** (default port 5432). Create a database and
user, for example in `psql` or pgAdmin:

```sql
CREATE USER chatbot WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE university_chatbot OWNER chatbot;
ALTER USER chatbot CREATEDB;   -- needed only to run the automated tests
```

Then set `DB_USER`, `DB_PASSWORD`, `DB_HOST=127.0.0.1` and `DB_PORT=5432` in `.env`.

**Option B: a project-local cluster (used during development of this project).** This needs
no administrator rights or service changes, and runs on port 5433 with local trust
authentication:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\initdb.exe" -D .pgdata -U chatbot --auth=trust -E UTF8 --locale=C
powershell -ExecutionPolicy Bypass -File scripts\start_database.ps1
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -h 127.0.0.1 -p 5433 -U chatbot university_chatbot
```

After a reboot, start it again with `scripts\start_database.ps1`, and stop it with
`scripts\stop_database.ps1`. Trust authentication only accepts connections from the local
machine. Use Option A with a password for anything beyond local development.

### 10.3 Environment configuration

```powershell
copy .env.example .env
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Paste the generated key into `DJANGO_SECRET_KEY` and fill in the database settings. All
settings are documented in `.env.example`. The most important ones:

| Variable | Default | Meaning |
|---|---|---|
| `CHATBOT_DEMO_MODE` | `true` | Allow clearly labelled demonstration information |
| `CHATBOT_SIMILARITY_THRESHOLD` | `0.50` | Minimum cosine similarity for an answer |
| `NLP_OFFLINE` | `false` in example | Set to `true` after the model is downloaded |
| `NLP_BACKEND` | `onnx` | `onnx` (fast start-up) or `torch` (sentence-transformers on PyTorch) |
| `NLP_THREADS` | `0` (auto) | CPU threads used for inference |
| `DB_POOL` | `true` | PostgreSQL connection pool |
| `CORS_ALLOWED_ORIGINS` | localhost:3000, 5173 | Origins of the future frontend |

### 10.4 Download the model (once, needs internet)

```powershell
python manage.py download_model
```

The model (about 90 MB) is stored in `./ml_models`. Then set `NLP_OFFLINE=true` in `.env`.
From then on the backend runs without any internet connection.

### 10.5 Migrate and import the dataset

```powershell
python manage.py migrate
python manage.py import_faqs
python manage.py evaluate_retrieval        # optional: retrieval accuracy and threshold report
```

### 10.6 Create an administrator account

```powershell
python manage.py createsuperuser
```

Superusers automatically get the `administrator` role. They can use Django Admin
(`/admin/`) and the administrator API endpoints. An administrator can also promote another
user with `PATCH /api/auth/users/{id}/ {"role": "administrator"}`.

## 11. Running the application

```powershell
.venv\Scripts\activate
powershell -ExecutionPolicy Bypass -File scripts\start_database.ps1   # only for Option B
python manage.py runserver
```

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/api/ | REST API root (see section 12) |
| http://127.0.0.1:8000/api/docs/ | Swagger UI (interactive API documentation) |
| http://127.0.0.1:8000/api/redoc/ | ReDoc documentation |
| http://127.0.0.1:8000/api/schema/ | OpenAPI 3 schema (import into Postman) |
| http://127.0.0.1:8000/api/health/ | Database and model status |
| http://127.0.0.1:8000/admin/ | Django Admin (knowledge base management) |

Useful management commands:

| Command | Purpose |
|---|---|
| `download_model` | Download and verify the local model |
| `import_faqs [path]` | Validate and import or update the dataset |
| `rebuild_embeddings [--force]` | Regenerate missing, outdated or (with `--force`) all embeddings |
| `evaluate_retrieval [--verbose-errors]` | Measure accuracy and recommend a threshold |

### Testing the API with Postman

1. In Postman choose **Import → Link** and enter `http://127.0.0.1:8000/api/schema/`. This
   creates a collection with every endpoint.
2. **Guest:** send `POST /api/chat/conversations/` with body `{}`. Copy `guest_token` from the
   response and add a header `X-Guest-Token: <token>` to later requests.
3. **Registered user:** `POST /api/auth/register/` or `POST /api/auth/login/`, then add a header
   `Authorization: Token <token>`.
4. Ask a question: `POST /api/chat/conversations/{id}/messages/` with
   `{"content": "Which courses can I study?"}`.

## 12. API documentation

All endpoints are under `/api/`. Authentication uses the `Authorization: Token <key>` header.
Guests use `X-Guest-Token`. List endpoints are paginated (`?page=`, `?page_size=` up to 100).

### 12.1 Endpoints

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/api/auth/register/` | public | Register (role `student` or `prospective_student`); returns token |
| POST | `/api/auth/login/` | public | Log in with username **or** e-mail; returns token |
| POST | `/api/auth/logout/` | user | Delete the token |
| GET / PATCH | `/api/auth/profile/` | user | View or update own profile (role is read-only) |
| POST | `/api/auth/password/change/` | user | Change password (rotates the token) |
| GET / PATCH | `/api/auth/users/`, `/api/auth/users/{id}/` | admin | Manage roles and account status |
| POST | `/api/chat/conversations/` | guest/user | Start a conversation (guests receive `guest_token`) |
| GET | `/api/chat/conversations/` | owner | List own conversations (`?status=`) |
| GET / PATCH / DELETE | `/api/chat/conversations/{id}/` | owner | Retrieve, rename or archive, delete |
| POST | `/api/chat/conversations/{id}/messages/` | owner | **Ask the chatbot** (runs the NLP pipeline) |
| GET | `/api/chat/conversations/{id}/messages/` | owner | Conversation history |
| POST | `/api/chat/conversations/claim/` | user | Move guest conversations (`X-Guest-Token`) to the account |
| GET | `/api/knowledge/categories/` (`/{id}/`) | public; write: admin | Categories (CRUD for admins) |
| GET | `/api/knowledge/faqs/` (`/{id}/`) | public; write: admin | FAQs. Filters: `category`, `search`, `information_type`; admins also `verification_status`, `publication_status` |
| POST | `/api/knowledge/faqs/{id}/archive/` | admin | Archive an FAQ |
| POST | `/api/knowledge/faqs/{id}/regenerate-embeddings/` | admin | Force embedding regeneration |
| CRUD | `/api/knowledge/alternative-questions/` | admin | Alternative formulations (`?faq=`) |
| GET | `/api/knowledge/articles/` (`/{id}/`) | public; write: admin | Knowledge articles |
| GET | `/api/knowledge/search/?q=&type=all\|faq\|article&limit=` | public | Semantic search with scores |
| POST | `/api/feedback/` | owner of the message | Rate a chatbot response (1–5) with optional comment |
| GET | `/api/feedback/?sentiment=positive\|negative` | admin | List feedback with the question and response |
| GET | `/api/analytics/overview/` | admin | Users, conversations, messages, questions, answered or unanswered, answer rate, average response time, feedback |
| GET | `/api/analytics/popular-questions/` | admin | Most frequently answered FAQs and most frequent phrasings |
| GET / PATCH | `/api/analytics/unanswered-questions/` (`/{id}/`) | admin | Knowledge gaps; set `review_status` (resolved/dismissed), `resolved_faq`, `admin_notes` |
| GET | `/api/analytics/unanswered-questions/summary/` | admin | Pending unanswered questions grouped by wording |
| GET | `/api/analytics/category-statistics/` | admin | Questions, similarity and feedback per category and per intent |
| GET | `/api/analytics/response-performance/` | admin | Average, min, max, median and p95 response time; daily and monthly usage |
| GET | `/api/analytics/usage/` | admin | Daily and monthly usage |
| GET | `/api/health/` | public | Database and model status |

All analytics endpoints accept `start_date` and `end_date` (YYYY-MM-DD, inclusive) and
`limit`.

### 12.2 Example: guest conversation

```http
POST /api/chat/conversations/
Content-Type: application/json

{}
```

```json
HTTP/1.1 201 Created
{
  "id": 8, "title": "", "status": "active", "is_guest": true, "message_count": 0,
  "created_at": "2026-11-07T22:10:39.106400+02:00",
  "updated_at": "2026-11-07T22:10:39.106400+02:00",
  "guest_token": "<secret token, shown only once>"
}
```

### 12.3 Example: answered question (real response from the running server)

```http
POST /api/chat/conversations/8/messages/
X-Guest-Token: <secret token>
Content-Type: application/json

{"content": "Which courses can I study?"}
```

```json
HTTP/1.1 201 Created
{
  "success": true,
  "conversation_id": 8,
  "user_message": {"id": 267, "content": "Which courses can I study?", "timestamp": "2026-11-07T20:10:39.122012Z"},
  "bot_response": {
    "id": 268,
    "content": "In this demonstration dataset, the university is described as offering undergraduate programmes in areas such as education, business and management, information technology and social sciences, ... should be confirmed with the Admissions Office.\n\n[Demonstration information] This is hypothetical demonstration information prepared for an academic prototype. It is not official information from DMI St. John the Baptist University. Please confirm with the university.",
    "intent": "programme_enquiry",
    "intent_confidence": 0.8229,
    "similarity_score": 0.8527,
    "answered": true,
    "response_type": "answer",
    "information_type": "demonstration",
    "verification_status": "unverified",
    "is_verified": false,
    "disclaimer": "This is hypothetical demonstration information prepared for an academic prototype. It is not official information from DMI St. John the Baptist University. Please confirm with the university.",
    "sources": [{
      "type": "faq", "id": 6, "reference_code": "PROG-001",
      "question": "What programmes does the university offer?",
      "category": "Academic Programmes",
      "source_description": "Hypothetical demonstration data prepared for the AI Powered University Chatbot academic prototype. Not verified with DMI St. John the Baptist University.",
      "source_url": null, "information_type": "demonstration", "verification_status": "unverified"
    }],
    "suggestions": [],
    "matched_question": "Which courses can I study here?",
    "used_context": false,
    "response_time_ms": 5.38,
    "timestamp": "2026-11-07T20:10:39.122012Z"
  }
}
```

### 12.4 Example: unanswered question

```json
{
  "success": true,
  "conversation_id": 8,
  "user_message": {"id": 269, "content": "What is the capital of Japan?", "timestamp": "..."},
  "bot_response": {
    "id": 270,
    "content": "I'm sorry, I couldn't find verified information about that question in the university knowledge base. Please contact the relevant university department for assistance.",
    "intent": "unknown", "similarity_score": 0.2648,
    "answered": false, "response_type": "fallback",
    "information_type": null, "is_verified": null, "disclaimer": null,
    "sources": [], "suggestions": [], "matched_question": null,
    "used_context": false, "response_time_ms": 14.63, "timestamp": "..."
  }
}
```

### 12.5 Example: registration, login and feedback

```http
POST /api/auth/register/
{"username": "chifundo", "email": "chifundo@example.com", "password": "<strong password>",
 "password_confirm": "<strong password>", "role": "student"}

→ 201 {"success": true, "token": "9944b0...", "user": {"id": 3, "username": "chifundo", "role": "student", ...}}

POST /api/feedback/
Authorization: Token 9944b0...
{"message": 268, "rating": 5, "comment": "Helpful"}

→ 201 {"id": 1, "message": 268, "rating": 5, "comment": "Helpful", "sentiment": "positive", "created_at": "..."}
```

### 12.6 Errors

Every error has the same shape, and internal details (stack traces, SQL) are never returned:

```json
HTTP/1.1 400 Bad Request
{"success": false, "error": {"code": "validation_error", "message": "content: Please enter a question.",
                             "details": {"content": ["Please enter a question."]}}}
```

| Status | When |
|---|---|
| 400 | Invalid input (empty or too-long question, wrong rating, invalid dates, etc.) |
| 401 / 403 | Not authenticated / not allowed (for example a non-admin calling analytics) |
| 404 | Not found **or not yours** (other users' conversations are invisible) |
| 405 | Method not allowed |
| 409 | Deleting a category that still has records |
| 429 | Rate limit exceeded (`retry_after_seconds` included) |
| 503 | Language model unavailable on the server |
| 500 | Unexpected error (generic message; details logged server-side) |

### 12.7 Security summary

* Passwords hashed with Django's PBKDF2 hasher and validated by Django's password validators.
* Token authentication. Tokens are deleted on logout and rotated on password change.
* Roles: administrator, student, prospective student and guest (unauthenticated). Users cannot
  register as administrators or change their own role.
* Ownership checks: users only see their own conversations. Guests are identified by a random
  256-bit token, of which only a SHA-256 hash is stored.
* Rate limiting (DRF throttling): anonymous 120/min, users 300/min, chat questions 30/min,
  login and registration 10/min, feedback 30/min. All configurable.
* Input validation and length limits on every endpoint. ORM-only database access.
* CORS restricted to configured frontend origins (the `X-Guest-Token` header is allowed). CSRF
  protection remains active for session-authenticated requests.
* Secrets only in `.env` (excluded from version control by `.gitignore`). `.env.example`
  contains placeholders only.
* With `DJANGO_DEBUG=false`, a secret key is mandatory and secure cookies are enabled.

## 13. Testing

```powershell
python manage.py test
```

The suite (106 tests) runs against a temporary PostgreSQL test database and uses the **real
local model**, not mocks, for all semantic tests. The database user needs the `CREATEDB`
permission. On the development laptop it takes one to three minutes. The test that compares
the ONNX and PyTorch backends deliberately loads PyTorch, and it is skipped if PyTorch is not
installed.

Coverage by area:

| Area | Examples of what is tested |
|---|---|
| Paraphrase retrieval | "What programmes does the university offer?", "Which courses can I study?", "What academic programmes are available?" all return PROG-001 with identical content; admission and other held-out paraphrases |
| Unrelated questions | Cake, football, Japan, movie questions all receive the fallback and are logged as unanswered |
| Thresholds and clarification | Raising the threshold forces a fallback; near-identical FAQs trigger clarification; intent tie-breaking |
| Verification | Demonstration answers are labelled; official mode returns only verified institutional records, without a disclaimer; demonstration information cannot be verified |
| Embeddings | 384 dimensions, unit length, caching, offline loading, missing-model error, automatic refresh on edit, no re-encoding when the text is unchanged, archived or deleted FAQs excluded |
| Import | Counts, repeat import creates no duplicates, invalid files rejected atomically, updates applied |
| Conversations | CRUD, history, title generation, guest isolation and claiming, ownership (404 for others), validation, archived conversations, follow-up context |
| Auth and permissions | Registration rules, password hashing, login by e-mail, logout, profile, password change, role restrictions, admin-only endpoints |
| Feedback and analytics | Ownership checks, duplicates, admin listing; every statistic checked against database counts; date filters; unanswered-question workflow |
| Robustness | Rate limiting (429), model unavailable (503, nothing saved), unexpected errors return no internal details |

## 14. Performance on the development laptop

Measured on the target machine (Intel Core i5 11th Gen, 12 GB RAM, Intel Iris Xe, SSD,
Windows 11), CPU only.

### 14.1 Why the first version felt slow

Answering a question has always been fast (the embedding, search and response take
milliseconds). The delay users saw was **start-up**: before the first answer, Python had to load
PyTorch, Hugging Face Transformers, sentence-transformers and scikit-learn. On a cold Windows
file cache (after a reboot or a long idle period), each of those files is read from disk and
scanned by antivirus. Measured stage by stage:

| Start-up stage | Cold cache | Warm cache |
|---|---|---|
| Django and project imports (incl. scikit-learn, SciPy, pandas) | 44.9 s | 2.5 s |
| `import torch` | 29.7 s | 2.2 s |
| `import transformers` | 41.6 s | 2.2 s |
| `import sentence_transformers` | 25.3 s | 2.9 s |
| Load model weights | 5.0 s | 0.3 s |
| Answer a question | 0.01 s | 0.01 s |
| **Total before the first answer** | **≈ 152 s** | **≈ 10.4 s** |

### 14.2 What was changed

* **ONNX Runtime instead of PyTorch** for the same model, with identical embeddings (section 6.2).
* **NumPy cosine similarity instead of scikit-learn**, which also removes SciPy and pandas.
* **Search index built during start-up warm-up**, so the first question does not pay for it.

Python now loads **791 files (86 MB) instead of 4,249 files (184 MB)** to start the server.

### 14.3 Results

| Measurement | Before | After |
|---|---|---|
| Start-up to "ready", warm cache (stage timing) | 10.4 s | **1.2 s** |
| Server process start to model ready (HTTP health check) | ~15 s | **2.7 s** |
| Start-up after a reboot (cold cache) | up to ~2.5 min | expected to fall roughly in line with the 81% fewer files; not measurable on demand |
| First question right after start-up | waited for warm-up (up to minutes) | **78 ms** |
| Typical question, full HTTP round trip (median / p95) | 57 ms / – | **15 ms / 35 ms** |
| Chatbot pipeline per question (median) | 16 ms | **8 ms** |
| Server memory | ~600 MB | **225 MB** |
| Retrieval accuracy (held-out set, section 7.4) | 92.7% top-1 | **92.7% top-1, identical results** |

### 14.4 Other optimisations

* Model loaded once per process and preloaded in a background thread, together with the intent
  examples and the search index. Offline mode means no network checks at start-up.
* Inference threads capped at the physical core count.
* Embeddings persisted in PostgreSQL and only recomputed when text changes. In-memory search
  matrix. Query embedding cache.
* **PostgreSQL connection pooling**. On this machine each new connection cost about 50 ms, and
  the development server opens a thread per request. Pooling cut a simple request from about
  86 ms to about 3 ms.
* `DB_HOST=127.0.0.1` instead of `localhost`, which avoids an IPv6 lookup costing about 13 ms
  per connection.
* Database indexes on status fields, timestamps and conversation history. Pagination on every
  list.

While the model loads, `GET /api/health/` reports `nlp_model.status` as `loading`, then
`ready`, and the web interface tells users their first answer may take a moment.

## 15. Known limitations

* **The dataset is hypothetical.** None of the 57 FAQs is verified university information.
  Before real use, each record must be checked with the university, converted to
  `institutional`/`verified`, and demo mode switched off.
* Retrieval accuracy on the held-out set is 92.7% top-1. The known errors are near-neighbour
  FAQs (for example *instalments* versus *payment methods*). Accuracy improves as alternative
  formulations are added.
* all-MiniLM-L6-v2 is an English model. Questions in Chichewa are not understood reliably
  (only a couple of Chichewa greetings are handled by the small-talk rules).
* Context handling covers one previous topic and simple follow-up patterns. It is not a full
  dialogue manager.
* The chatbot returns whole stored answers. It does not combine information from several FAQs
  in one reply.
* The search index and caches are per process. With several server processes, each holds its
  own copy (about 0.5 MB of vectors), which is fine at this scale. Rate-limit counters use the
  local-memory cache, so they are per process too. Use Redis for multi-process production
  deployments.
* Embeddings are stored as JSON. This is ideal for hundreds of records, but not for hundreds of
  thousands.
* `runserver` is a development server. For deployment on Windows use a WSGI server such as
  `waitress`, or `gunicorn` on Linux, behind HTTPS.
* The evaluation set (75 questions) is small and was written by the developer. The 0.50
  threshold should be re-checked with real user questions using `evaluate_retrieval` and the
  unanswered-question analytics.

## 16. Future improvements

* Load verified institutional information and run in official mode.
* Use logged unanswered and clarification questions (already collected) to add FAQs and
  alternative formulations, then re-evaluate the threshold.
* Optional `pgvector` column with an HNSW index if the knowledge base grows to many thousands of
  entries.
* A multilingual model (for example `paraphrase-multilingual-MiniLM-L12-v2`) for Chichewa
  support.
* Optional, grounded LLM paraphrasing of retrieved answers, behind `ResponseGenerator`.
* Redis cache for shared rate limiting and caching across processes. Background task queue for
  bulk embedding jobs.
* Frontend application (separate project, consuming this API).

## 17. Web interface (Campus Desk)

`frontend/` contains the user interface: a React 19 + TypeScript single-page app built with
Vite. It talks to the backend only through the REST API above.

### 17.1 Screens

| Route | Who | What it does |
|---|---|---|
| `/` | everyone | Welcome screen: a greeting, a large question box, and a tiled index of topics with real example questions to tap |
| `/c/:id` | owner | A conversation. Answers type themselves out and show their topic, a **Demo information** badge, a match-strength indicator, an expandable source panel, copy and Helpful / Not helpful buttons, and up to three **related questions** as follow-up chips. Clarifications offer options; fallbacks link to the topics page |
| `/topics` | everyone | Every published answer grouped by topic, with a word filter and topic pills. Each answer can be continued in the chat |
| `/signin` | everyone | Sign in (username or e-mail) or create an account (prospective or current student). Guest conversations move into the account automatically |
| `/staff` | administrators | Dashboard: answer-rate ring, conversations, response time and feedback tiles, questions per day (line chart with a table fallback), a "Needs attention" queue for unanswered questions, most-asked questions and answers by topic |

Every page except sign-in shares a side panel with **New chat**, **quick search** (`Ctrl+K`,
or `⌘K` on a Mac: semantic search over the knowledge base, opening the chosen answer in the
chat), navigation, recent conversations (rename and delete), a prototype notice, the account and
the theme toggle. On phones the panel becomes a drawer. Guests are fully supported via the
`X-Guest-Token` session.

The follow-up chips use the `related_questions` field that the message endpoints return: the
FAQs whose questions are closest in meaning to the one that was answered.

### 17.2 Design

* **Direction:** "Modern campus". A forest-green side panel and feature tiles, one warm gold
  accent, soft layered cards on a dotted paper background, and a small sun-over-hills
  illustration.
* **Type:** Bricolage Grotesque (headings) with Hanken Grotesk (text), both self-hosted, so
  there are no third-party font requests.
* **Colour:** OKLCH design tokens in `frontend/src/styles/tokens.css`, with a light theme by
  default and a dark theme that follows the device or the toggle. Gold dashed badges are
  reserved for demonstration-information labels.
* **Motion:** short entrance animations, press feedback on buttons, a "searching the knowledge
  base" indicator and typed-out answers. Answers are retrieved whole, so the typing is a
  presentation effect. All motion is removed when the device asks for reduced motion.
* **Accessibility (measured):** 23 text and background colour pairs checked in both themes, all
  at least 4.6:1 (WCAG AA). Full keyboard use, visible focus, a skip link, screen-reader
  announcements for new answers, 44 px touch targets on touch screens, IME-safe Enter-to-send,
  and no horizontal scrolling at 375 px.

### 17.3 Running it

Requires Node.js 20 or newer. Start the backend first (section 11), then:

```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The Vite development server proxies `/api` and `/admin` to Django at `http://127.0.0.1:8000`
(override with `VITE_BACKEND_URL`), so no CORS setup is needed during development.

For deployment, run `npm run build` and serve `frontend/dist/` from the same origin as the API
(for example behind one web server that routes `/api/` and `/admin/` to Django and everything
else to `index.html`). If the interface is hosted on a different origin, add that origin to
`CORS_ALLOWED_ORIGINS` and change the API base URL in `frontend/src/api/client.ts`.

### 17.4 Notes

* Right after a server restart the language model needs a few seconds to load (see section 14).
  The interface says so in the message box instead of leaving users guessing.
* Feedback can be given once per answer. After a page reload the buttons reappear, but a second
  rating is politely ignored.
