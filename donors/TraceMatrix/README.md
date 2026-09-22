# 🔍 OSINT Stack (100% Open-Source) — Dockerized

A fully **open-source** OSINT (Open Source Intelligence) stack that combines modern search technologies, scraping, and data analysis.

## 📦 What's Included

### Core Services

- **🎯 Orchestrator (FastAPI)** — Central API with multiple connectors:
    - Google Custom Search Engine (CSE)
    - SearXNG integration (metasearch engine)
    - Reacher (email verification)
    - Social-Analyzer (username OSINT)
    - Trafilatura (intelligent web scraping)
    - Sentence-Transformers (semantic embeddings)

- **🔎 OpenSearch** — Full-text search with:
    - BM25 ranking algorithm
    - k-NN vector search
    - Hybrid Search with RRF (Reciprocal Rank Fusion)

- **📊 OpenSearch Dashboards** — Web UI for visualization and exploration
- **🌐 SearXNG** — Privacy-respecting metasearch engine
- **✉️ Reacher** — Email verification service
- **🔗 Social-Analyzer** — Username enumeration across 1000+ platforms
- **⚡ Redis** — Caching layer for performance

### Key Features

✅ Web scraping with semantic analysis  
✅ Hybrid search (BM25 + vector embeddings)  
✅ Email verification  
✅ Social media username enumeration  
✅ CSV export for Maltego CE integration (now includes **images & documents** metadata)  
✅ 100% open-source stack

---

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose installed
- (Optional) Google Programmable Search API credentials

### Installation Steps

**1. Clone the repository:**
```bash
git clone <repo-url>
cd Osint
```

**2. Environment Variables Setup:**

Copy `.env.example` to `.env` and fill in your credentials:

```bash
# Linux/Mac
cp .env.example .env
```

Open `.env` and change the values:

```env
# Google Custom Search Engine (optional)
GOOGLE_CSE_API_KEY=your_google_cse_api_key_here
GOOGLE_CSE_CX=your_google_cse_cx_here

# SearXNG Secret (change to a random string)
SEARXNG_SECRET_KEY=change_this_to_a_random_string
# SearXNG Base URL (used by Orchestrator when calling the JSON API)
SEARXNG_BASE_URL=http://searxng:8080

# OpenSearch Password (change to a strong password)
OPENSEARCH_INITIAL_ADMIN_PASSWORD=change_this_to_a_strong_password

# The rest can remain as they are
```

> ⚠️ **IMPORTANT:** Don't commit the `.env` file! It's already in `.gitignore` for your security.

> 💡 If you don't set the Google CSE credentials, the `/search` endpoint will work with limited capabilities (SearXNG only).

**3. Start the stack:**
```bash
docker compose up --build
```

Wait until all services are up (~2-3 minutes for the first time).

---

## 🌐 Available Services

| Service | URL | Description |
|---------|-----|-----------|
| **Orchestrator API** | http://localhost:8000/docs | FastAPI Swagger UI (interactive docs) |
| **SearXNG** | http://localhost:8081 | Metasearch engine interface |
| **OpenSearch** | http://localhost:9200 | Search engine API |
| **OpenSearch Dashboards** | http://localhost:5601 | Data visualization & exploration |
| **Reacher** | http://localhost:8082 | Email verification service |
| **Social-Analyzer** | http://localhost:9005 | Username enumeration tool |
| **PhoneInfoga** | http://localhost:8083 | Phone number OSINT tool |

---

## 📡 API Endpoints

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-----------|
| `/orchestrate` | POST | **Multi-step OSINT workflow**: search → extract entities → verify → enrich → export |
| `/search` | POST | Basic search with Google CSE / SearXNG + profession filtering |
| `/verify_email` | POST | Email verification via Reacher |
| `/ingest_urls` | POST | Scraping, embedding generation & OpenSearch indexing |
| `/search_hybrid` | POST | Hybrid search (BM25 + k-NN + RRF fusion) |
| `/social_lookup` | POST | Username enumeration across 1000+ social platforms |
| `/phone_lookup` | POST | Phone number OSINT via PhoneInfoga |
| `/harvest_email` | POST | Email & subdomain harvesting via theHarvester |
| `/export_csv` | GET | Export data in CSV format for Maltego |

For **full documentation** and **interactive testing**, open Swagger UI: http://localhost:8000/docs

---

## 🧪 Testing (Docker)

You can run tests inside the same image the Orchestrator uses:

```bash
# ephemeral test run
docker compose run --rm orchestrator bash -c "pip install -U pytest pytest-asyncio respx && pytest -q"
```

Or define a dedicated test service (optional) and run:
```bash
docker compose run --rm orchestrator-tests
# or
docker compose --profile tests up --build orchestrator-tests
```

---

## 💡 Usage Examples

### 🎯 Orchestrate — Full OSINT Workflow (Recommended)

The `/orchestrate` endpoint is the most powerful feature, combining all services in a multi-step workflow:

**Fields:** `name`, `keywords`, `phone` (optional), limits...

**Behavior:**
- Runs initial web search, extracts emails & usernames, runs social lookups and email checks, performs hybrid search (BM25+kNN), ingests URLs, and exports CSV for Maltego.
- **Phone handling:** If `phone` is NOT provided, the system will NOT include it in the initial search. Instead, it attempts to discover phone numbers from initial results (snippets/titles/URLs) and, if found, uses them downstream (PhoneInfoga & hybrid query), limited by `phone_limit`.

**Params (limits):**
- `search_limit`, `social_limit`, `email_limit`, `hybrid_k`, `ingest_limit`, `export_limit`
- `phone_limit` (how many discovered phones to use when `phone` is not provided)

**Example:**

```bash
curl -sS -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Panagiotis Drakatos",
    "keywords": ["athens","software engineer","keyword-only orchestration"],
    "search_limit": 15,
    "social_limit": 10,
    "email_limit": 20,
    "phone_limit": 5,
    "hybrid_k": 20,
    "ingest_limit": 60,
    "export_limit": 2000,
    "fallback": true
  }' | jq .
```

**With phone number:**

```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["athens", "security"],
    "phone": "+3069XXXXXXXX",
    "search_limit": 15,
    "social_limit": 10,
    "email_limit": 20,
    "phone_limit": 5,
    "hybrid_k": 20,
    "ingest_limit": 60,
    "export_limit": 2000
  }'
```

**Response includes:**
- `counts`: Statistics on discovered entities (URLs, emails, usernames, phones)
- `samples`: Preview of discovered entities
- `phones_found`: List of discovered phone numbers (if phone not provided)
- `phones_considered`: Phones used for downstream enrichment
- `phoneinfoga`: PhoneInfoga results for each phone
- `social`: Social media profile lookups
- `emails`: Email verification results
- `ingested`: URLs successfully indexed in OpenSearch
- `csv_path`: Path to exported CSV for Maltego

---

### 🔎 Web Search with Profession Filtering

```bash
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["architect"],
    "limit": 5
  }'
```

### 🔗 Social Media Username Lookup

```bash
curl -X POST "http://localhost:8000/social_lookup" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe"
  }'
```

### 📥 Ingest & Index URLs

```bash
curl -X POST "http://localhost:8000/ingest_urls" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com/portfolio"],
    "source": "web"
  }'
```

### 🎯 Hybrid Search (BM25 + Vector)

```bash
curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "John Doe architect Athens",
    "k": 10
  }'
```

### ✉️ Email Verification

```bash
curl -X POST "http://localhost:8000/verify_email" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "example@domain.com"
  }'
```

### 📱 Phone Number Lookup

```bash
# Via Orchestrator API
curl -X POST "http://localhost:8000/phone_lookup" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+306912345678"
  }'

# Direct PhoneInfoga API
curl -X GET "http://localhost:8083/api/numbers/+306912345678"
```

**Note:** Phone numbers must be in international format (E.164), e.g., `+306912345678` for Greece, `+14155552671` for USA.

### 📊 Export for Maltego CE

```bash
curl "http://localhost:8000/export_csv"
```

The file is created at: `orchestrator/exports/entities.csv`

**Import into Maltego CE:**
1. Open Maltego CE
2. Go to **Import** → **CSV**
3. Select the `entities.csv` file
4. Map fields according to instructions

---

## 🎯 Workflows & Use Cases

### When to use which endpoint?

#### 1️⃣ I want to simply check if someone exists + their role/profession

**Steps:**
```bash
# 1. Basic search with name + keywords
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["architect"],
    "limit": 10
  }'

# 2. (Optional) Verify email if found
curl -X POST "http://localhost:8000/verify_email" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john.doe@example.com"
  }'

# 3. (Optional) Social lookup for footprints
curl -X POST "http://localhost:8000/social_lookup" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe"
  }'
```

**Why this approach?**
- ✅ Minimal friction, fast results
- ✅ Low cost (Google CSE quota)
- ✅ Ideal for quick checks

---

#### 2️⃣ I want usernames/profiles from multiple platforms

**Steps:**
```bash
# Go directly to Social-Analyzer
curl -X POST "http://localhost:8000/social_lookup" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe"
  }'
```

**Why this approach?**
- ✅ Targeted for social media
- ✅ No Google quota usage
- ✅ Often cleaner hits for handles
- ✅ 1000+ platforms in one call

---

#### 3️⃣ I want high accuracy and fast follow-up queries without additional costs

**Steps:**
```bash
# 1. Collect the best pages (URLs)
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["architect", "Athens"],
    "limit": 20
  }'

# 2. Ingest the URLs (batch processing)
curl -X POST "http://localhost:8000/ingest_urls" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://example.com/profile1",
      "https://example.com/profile2",
      "https://linkedin.com/in/...",
      "... (20-200 URLs)"
    ],
    "source": "web_search"
  }'

# 3. Run multiple searches with hybrid search (fast & free)
curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "John Doe architect Athens portfolio",
    "k": 10
  }'

curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "architectural projects Greece 2024",
    "k": 10
  }'
```

**Why this approach?**
- ✅ After initial ingest, searches are very fast
- ✅ Doesn't consume Google quota for follow-up queries
- ✅ Ranking improves (BM25 + k-NN + RRF)
- ✅ Ideal for deep research

---

#### 4️⃣ I want a graph/report

**Steps:**
```bash
# When you've finalized entities, export to CSV
curl "http://localhost:8000/export_csv" -o entities.csv

# Open in Maltego CE:
# 1. Maltego CE → Import → CSV
# 2. Select entities.csv
# 3. Map fields (name, url, source, etc.)
# 4. Visualize the graph
```

**Why this approach?**
- ✅ Not needed for every run
- ✅ Only for export/visualization
- ✅ Ideal for presentations/reports

---

## 📋 2 Recommended "Recipes"

### Recipe A: Quick Lookup (3 calls max)

**Use case:** Quick verification of person's existence

```bash
# Step 1: Web search
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","keywords":["architect"],"limit":15}'

# Step 2: Social lookup
curl -X POST "http://localhost:8000/social_lookup" \
  -H "Content-Type: application/json" \
  -d '{"username":"johndoe"}'

# Step 3: Email verification (only for candidate emails)
curl -X POST "http://localhost:8000/verify_email" \
  -H "Content-Type: application/json" \
  -d '{"email":"john.doe@example.com"}'

# Optional Step 4: Phone lookup (if phone number found)
curl -X POST "http://localhost:8000/phone_lookup" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+306912345678"}'
```

**⏱️ Time:** 30-60 seconds  
**💰 Cost:** Low (uses Google only once)  
**🎯 Ideal for:** Initial reconnaissance, quick checks

---

### Recipe B: Deep Research + Fast Follow-up Runs (Index-First)

**Use case:** Deep investigation with multiple queries

```bash
# Step 1: Initial search for URLs
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","keywords":["architect"],"limit":50}'

# Step 2: Batch ingest (20-200 URLs)
curl -X POST "http://localhost:8000/ingest_urls" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://site1.com/profile",
      "https://site2.com/portfolio",
      "... (50-200 URLs)"
    ],
    "source": "batch_research"
  }'

# Step 3: Multiple hybrid searches (fast, no additional cost)
curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"architectural projects Athens 2024","k":10}'

curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"sustainable building design Greece","k":10}'

curl -X POST "http://localhost:8000/search_hybrid" \
  -H "Content-Type: application/json" \
  -d '{"query":"John Doe awards publications","k":10}'

# Step 4: Export for reporting (if needed)
curl "http://localhost:8000/export_csv" -o final_report.csv
```

**⏱️ Time:** 5-15 minutes for setup, then <1 second/query  
**💰 Cost:** Mainly in first step, then nearly zero  
**🎯 Ideal for:** Deep investigations, research projects, multiple angles

---

## ⚡ Performance & Tips

### General Guidelines

- **Not everything is needed every time** — Combine `/search` + `/social_lookup` for most cases
- **Social lookup doesn't burn quotas** — But it runs many checks, so use timeouts if automating
- **Email precision** — Always pass candidate emails through `/verify_email` before considering them valid

### For Scaling/Speed

If you want to invest in `/ingest_urls` + `/search_hybrid`:

**1. Batch Size Optimization:**
```bash
# Optimal: 50-200 URLs per batch
curl -X POST "http://localhost:8000/ingest_urls" \
  -H "Content-Type: application/json" \
  -d '{"urls":[/* 50-200 URLs */],"source":"batch"}'
```

**2. Embedding Configuration:**
```bash
# In orchestrator/.env or environment:
EMBED_DIM=384  # For balance between speed/quality
# EMBED_DIM=768  # If you have RAM and want better accuracy
```

**3. Docker Resources:**
```yaml
# In docker-compose.yml:
services:
  orchestrator:
    deploy:
      resources:
        limits:
          memory: 4G  # Minimum for embeddings
  opensearch:
    deploy:
      resources:
        limits:
          memory: 2G  # For k-NN vectors
```

**Total recommended RAM:** 4-6GB for the entire stack

### Quota Control

**Caching for Google CSE** (reduce API calls):
```bash
# Redis is already in the stack - enable caching:
# In orchestrator/main.py, add TTL 7-30 days for search results
```

**Benefits:**
- ✅ Same query → instant response from cache
- ✅ Reduce Google CSE quota usage by ~60-80%
- ✅ Faster response times

---

## 🛠️ Extensions & Customization

This stack is a **starter template**. You can extend it with:

### Recommended Additional Tools

- **[Sherlock](https://github.com/sherlock-project/sherlock)** — Username search across 400+ social networks
- **[Maigret](https://github.com/soxoj/maigret)** — Collect info about person by username
- **[theHarvester](https://github.com/laramies/theHarvester)** — Email, subdomain & people intelligence (already included in stack)
- **[SpiderFoot](https://github.com/smicallef/spiderfoot)** — Automated OSINT reconnaissance
- **[Holehe](https://github.com/megadose/holehe)** — Check if email is used on different sites
- **[Holehe](https://github.com/megadose/holehe)** — Check if email is used on different sites

### Customization Tips

- Add your own connectors to the `orchestrator/` directory
- Modify profession filters in `profession_filter.py`
- Customize embedding models in `scrape_embed.py`
- Configure OpenSearch schema for your needs

---

## 📝 License

Open-source project. Use responsibly and in accordance with your country's laws.

## ⚠️ Disclaimer

This tool is for **legal OSINT research** and **educational purposes**. The user is responsible for the lawful use of this software.

---

## 🛠 Useful scripts (Unix/WSL only)

Run these from a Bash shell (Linux/macOS or Windows via WSL):
- Rebuild orchestrator: `bash scripts/rebuild_orchestrator.sh`
- Normalize SearX config + smoke test: `bash scripts/check_searx_config.sh`
- Generate secrets for .env: `bash scripts/generate_secrets.sh`
- Purge shell env history: `bash scripts/purge_env_history.sh`

Windows .bat scripts are deprecated.

---
