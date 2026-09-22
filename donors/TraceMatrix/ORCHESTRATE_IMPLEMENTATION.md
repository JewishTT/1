# Orchestrate Endpoint Implementation

## Summary

Successfully implemented a comprehensive `/orchestrate` endpoint that performs multi-step OSINT workflows with automatic entity extraction and enrichment.

## Key Features

### 1. Phone Number Extraction & Handling
- **Automatic Discovery**: If no phone number is provided in the request, the system automatically extracts phone numbers from search results (snippets, titles, URLs)
- **Smart Filtering**: Validates phone numbers to be between 8-15 digits
- **International Support**: Handles international formats with '+' prefix
- **Configurable Limit**: `phone_limit` parameter controls how many discovered phones to use

### 2. Multi-Step Workflow

The endpoint performs the following operations in sequence:

1. **Initial Search**
   - Searches with name + keywords
   - Includes phone number ONLY if provided by user
   - Extracts URLs, text snippets, and titles

2. **Entity Extraction**
   - **Emails**: Regex-based extraction from text
   - **Usernames**: Extracts from known social platforms (Twitter/X, GitHub, LinkedIn, Instagram, Facebook)
   - **Phone Numbers**: Extracts from text/URLs if not provided by user

3. **PhoneInfoga Lookups**
   - Parallel lookups for all phones (provided or discovered)
   - Optional via `include_phoneinfoga` flag

4. **Social Media Lookups**
   - Parallel username enumeration across 1000+ platforms
   - Uses Social-Analyzer integration

5. **Email Verification**
   - Parallel email verification via Reacher
   - Validates email deliverability

6. **Hybrid Search**
   - Enriched query with all discovered entities
   - BM25 + k-NN vector search with RRF fusion
   - Discovers novel URLs not in initial search

7. **URL Ingestion**
   - Scrapes and embeds novel URLs
   - Indexes in OpenSearch for future searches

8. **CSV Export**
   - Generates Maltego-compatible CSV
   - Includes all indexed entities

## API Reference

### Endpoint: `POST /orchestrate`

#### Request Body

```json
{
  "name": "John Doe",              // Optional: target person name
  "keywords": ["athens", "security"], // Optional: search keywords
  "phone": "+3069XXXXXXXX",        // Optional: phone in E.164 format
  "search_limit": 15,              // Initial search results
  "social_limit": 10,              // Max social profiles per username
  "email_limit": 20,               // Max emails to extract/verify
  "phone_limit": 5,                // Max phones to discover (if not provided)
  "hybrid_k": 20,                  // Hybrid search results
  "ingest_limit": 60,              // Max URLs to ingest
  "export_limit": 2000,            // Max rows in CSV export
  "include_phoneinfoga": true      // Enable PhoneInfoga lookups
}
```

#### Response Structure

```json
{
  "query": "John Doe athens security +3069XXXXXXXX username@example.com",
  "counts": {
    "initial_urls": 15,
    "hybrid_urls": 20,
    "novel_urls": 5,
    "emails_found": 3,
    "usernames_found": 2,
    "phones_found": 1
  },
  "samples": {
    "emails": ["user@example.com", "..."],
    "usernames": ["johndoe", "..."],
    "novel_urls": ["https://example.com", "..."]
  },
  "phones_found": ["+3069XXXXXXXX"],
  "phones_considered": ["+3069XXXXXXXX"],
  "phoneinfoga": [
    {
      "phone": "+3069XXXXXXXX",
      "result": { "valid": true, "carrier": "Cosmote", ... }
    }
  ],
  "social": [
    {
      "username": "johndoe",
      "result": { "detected": ["Twitter", "GitHub"], ... }
    }
  ],
  "emails": [
    {
      "email": "user@example.com",
      "result": { "is_reachable": "safe", "syntax": "valid", ... }
    }
  ],
  "ingested": {
    "ok": 5,
    "urls": ["https://novel1.com", "..."]
  },
  "csv_path": "exports/entities.csv"
}
```

## Implementation Details

### Helper Functions

1. **`_norm_phone(p)`**: Normalizes phone numbers (removes all non-digit characters except '+')
2. **`_extract_urls(items)`**: Extracts URLs from search result items
3. **`_extract_emails(texts)`**: Regex-based email extraction
4. **`_extract_usernames_from_urls(urls)`**: Extracts usernames from social media URLs
5. **`_extract_phones(texts)`**: Regex-based phone extraction with validation

### Regex Patterns

- **Email**: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`
- **Phone**: `(?:\+|00)?\s?(?:\d[\s\-\.\(\)]?){7,16}\d` (very permissive international pattern)

### Supported Social Platforms

- Twitter/X
- GitHub
- LinkedIn
- Instagram
- Facebook

Can be easily extended by adding entries to `KNOWN_USER_PATTERNS`.

## Usage Examples

### Example 1: Without Phone Number (Auto-Discovery)

```bash
curl -X POST "http://localhost:8000/orchestrate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "keywords": ["athens", "security"],
    "search_limit": 15,
    "social_limit": 10,
    "email_limit": 20,
    "phone_limit": 5,
    "hybrid_k": 20
  }'
```

**Behavior**: 
- System searches WITHOUT phone in initial query
- Attempts to discover phones from search results
- Uses discovered phones for PhoneInfoga lookups and hybrid search

### Example 2: With Phone Number

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
    "hybrid_k": 20
  }'
```

**Behavior**:
- System includes phone in initial search query
- Phone number is used for PhoneInfoga lookup
- No phone discovery is attempted

## Environment Variables

- `ORCHESTRATOR_BASE_URL`: Base URL for internal API calls (default: `http://127.0.0.1:8000`)
- `PHONEINFOGA_BASE_URL`: PhoneInfoga service URL (default: `http://phoneinfoga:8080`)

## Performance Considerations

- **Parallel Processing**: Social lookups, email verification, and PhoneInfoga lookups run in parallel using `asyncio.gather()`
- **Configurable Limits**: All limits are configurable to balance thoroughness vs. speed
- **Timeout**: HTTP client has 30-second timeout for all requests

## Error Handling

- Failed PhoneInfoga lookups return `{"phone": "...", "error": true}`
- Failed social lookups return `{"username": "...", "error": true}`
- Failed email verifications return `{"email": "...", "error": true}`
- CSV export errors return `"csv_path": "error"`

## Future Enhancements

1. Add more social platform patterns (Reddit, TikTok, etc.)
2. Implement caching for repeated entity lookups
3. Add webhook support for long-running operations
4. Export results in additional formats (JSON, XML)
5. Add result deduplication and entity resolution
6. Implement confidence scoring for extracted entities

## Files Modified

1. **`orchestrator/main.py`**
   - Added regex patterns for email/phone extraction
   - Added social platform username extraction patterns
   - Implemented helper functions for entity extraction
   - Added `OrchestrateRequest` model
   - Implemented `/orchestrate` endpoint with full workflow

2. **`README.md`**
   - Updated API endpoints table
   - Added comprehensive `/orchestrate` documentation
   - Added usage examples with and without phone

## Dependencies

All required dependencies are already in `requirements.txt`:
- `httpx` - Async HTTP client
- `asyncio` - Built-in async support
- `pydantic` - Request/response models
- `fastapi` - Web framework

## Testing

To test the endpoint:

1. Start the stack:
   ```bash
   docker compose up --build
   ```

2. Test with curl or Swagger UI at http://localhost:8000/docs

3. Check results in OpenSearch Dashboards at http://localhost:5601

