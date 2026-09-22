# Quick Start Guide - Orchestrate Endpoint

## What was implemented?

A powerful `/orchestrate` endpoint that performs a complete OSINT workflow automatically.

## Key Innovation: Smart Phone Discovery

**If you DON'T provide a phone number:**
- System WON'T include it in the initial search
- Will DISCOVER phone numbers from search results
- Uses discovered phones for PhoneInfoga lookups
- Limited by `phone_limit` parameter (default: 5)

**If you DO provide a phone number:**
- System INCLUDES it in the initial search query
- Uses it for PhoneInfoga lookup
- No phone discovery is attempted

## Quick Examples

### Minimal Request (Name Only)
```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe"}'
```

### With Keywords
```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["athens", "security"]
  }'
```

### With Phone (Full Example)
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
    "export_limit": 2000,
    "include_phoneinfoga": true
  }'
```

## What Happens Behind the Scenes?

1. **Initial Search** → Google CSE/SearXNG
2. **Extract Entities** → Emails, Usernames, Phones (if not provided)
3. **PhoneInfoga** → Parallel lookups for all phones
4. **Social Lookup** → Check usernames across 1000+ platforms
5. **Email Verification** → Validate emails with Reacher
6. **Hybrid Search** → BM25 + Vector search with all enriched data
7. **URL Ingestion** → Scrape and index novel URLs
8. **CSV Export** → Generate Maltego-compatible report

## All Configurable Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `name` | None | Target person name |
| `keywords` | [] | Search keywords |
| `phone` | None | Phone number (E.164 format) |
| `limit` | 25 | General result limit |
| `search_limit` | 10 | Initial search results |
| `social_limit` | 10 | Social profiles per username |
| `email_limit` | 20 | Max emails to extract/verify |
| `phone_limit` | 5 | Max phones to discover |
| `hybrid_k` | 15 | Hybrid search results |
| `ingest_limit` | 50 | Max URLs to scrape/index |
| `export_limit` | 1000 | Max CSV rows |
| `include_phoneinfoga` | true | Enable phone lookups |

## Response Structure

```json
{
  "query": "enriched search query with all entities",
  "counts": {
    "initial_urls": 10,
    "hybrid_urls": 15,
    "novel_urls": 5,
    "emails_found": 3,
    "usernames_found": 2,
    "phones_found": 1
  },
  "samples": {
    "emails": ["email1@example.com", "..."],
    "usernames": ["username1", "..."],
    "novel_urls": ["https://...", "..."]
  },
  "phones_found": ["+123456789"],
  "phones_considered": ["+123456789"],
  "phoneinfoga": [{"phone": "...", "result": {...}}],
  "social": [{"username": "...", "result": {...}}],
  "emails": [{"email": "...", "result": {...}}],
  "ingested": {"ok": 5, "urls": ["..."]},
  "csv_path": "exports/entities.csv"
}
```

## Supported Social Platforms (Username Extraction)

- Twitter / X
- GitHub
- LinkedIn
- Instagram
- Facebook

*Plus 1000+ platforms via Social-Analyzer lookup*

## Performance Tips

1. **Start Small**: Use lower limits for initial testing
2. **Adjust Timeouts**: Some lookups may take longer than 30s
3. **Use Parallel**: The endpoint already runs lookups in parallel
4. **Cache Results**: Consider caching for repeated searches

## Common Use Cases

### OSINT Investigation
```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Target Person",
    "keywords": ["location", "profession"],
    "search_limit": 20,
    "email_limit": 30
  }'
```

### Phone Number Investigation
```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+1234567890",
    "include_phoneinfoga": true
  }'
```

### Social Media Deep Dive
```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Username",
    "social_limit": 20,
    "ingest_limit": 100
  }'
```

## Environment Setup

Ensure these environment variables are set in your `.env` file:

```env
# Optional (defaults shown)
ORCHESTRATOR_BASE_URL=http://127.0.0.1:8000
PHONEINFOGA_BASE_URL=http://phoneinfoga:8080
```

## Testing

1. **Start the stack:**
   ```bash
   docker compose up --build
   ```

2. **Wait for services** (~2-3 minutes)

3. **Test with Swagger UI:**
   - Open: http://localhost:8000/docs
   - Find `/orchestrate` endpoint
   - Click "Try it out"
   - Fill in parameters
   - Execute

4. **Check results:**
   - CSV: `orchestrator/exports/entities.csv`
   - OpenSearch Dashboards: http://localhost:5601

## Troubleshooting

**Issue**: "Connection refused" errors
- **Solution**: Ensure all services are running (`docker compose ps`)

**Issue**: No results returned
- **Solution**: Check if Google CSE credentials are configured

**Issue**: PhoneInfoga errors
- **Solution**: Set `include_phoneinfoga: false` to disable

**Issue**: Timeout errors
- **Solution**: Reduce limits or increase timeout in code

## Next Steps

1. Review results in OpenSearch Dashboards
2. Import CSV into Maltego CE for visualization
3. Refine search with discovered entities
4. Use individual endpoints for deeper investigation

## Files Modified

- `orchestrator/main.py` - Added orchestrate endpoint
- `README.md` - Updated documentation
- `ORCHESTRATE_IMPLEMENTATION.md` - Detailed implementation notes
- `QUICKSTART_ORCHESTRATE.md` - This file

## Support

For issues or questions:
1. Check logs: `docker compose logs orchestrator`
2. Review Swagger UI docs: http://localhost:8000/docs
3. Test individual endpoints first before using orchestrate

