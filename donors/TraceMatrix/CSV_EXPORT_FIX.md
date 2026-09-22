# CSV Export Fixes - Διορθώσεις Εξαγωγής CSV

## Προβλήματα που Διορθώθηκαν

### 1. **Λάθος Path για CSV Αποθήκευση**
**Πρόβλημα:** Το CSV αποθηκευόταν στο `orchestrator/exports/` αντί για το `/app/exports/` που είναι το volume mount.

**Λύση:** Άλλαξε το path σε `/app/exports` για να αποθηκεύεται σωστά στον τοπικό φάκελο `./exports/`.

### 2. **Περιορισμένα Αποτελέσματα (50 μόνο)**
**Πρόβλημα:** Το endpoint `/export_csv` έπαιρνε μόνο 50 αποτελέσματα από το OpenSearch.

**Λύση:** 
- Προστέθηκε νέα συνάρτηση `get_all_docs()` που χρησιμοποιεί το Scroll API για να πάρει **ΟΛΕΣ** τις εγγραφές χωρίς περιορισμό
- Το `/export_csv` endpoint τώρα δέχεται προαιρετικό παράμετρο `limit`:
  - Χωρίς `limit`: Εξάγει **ΟΛΑ** τα documents
  - Με `limit`: Εξάγει μέχρι το όριο που ορίζεις (max 10,000 λόγω OpenSearch)

### 3. **FileExistsError Fix**
**Πρόβλημα:** `FileExistsError: [Errno 17] File exists: '/app/exports'` - το path υπήρχε ως file αντί για directory.

**Λύση:** Προστέθηκε έλεγχος που:
- Ελέγχει αν το path υπάρχει ως file και το διαγράφει
- Δημιουργεί το directory μόνο αν δεν υπάρχει

### 4. **Βελτιωμένο Output & Error Handling**
**Προσθήκες:**
- Content Preview: Πρώτοι 200 χαρακτήρες του περιεχομένου
- Καλύτερα μηνύματα απάντησης με συνολικό αριθμό εγγραφών
- Try-catch στο `get_all_docs()` για αδειανά indexes
- Έλεγχος ύπαρξης index πριν το scroll

## Χρήση

### Export ΟΛΩΝ των δεδομένων:
```bash
curl http://localhost:8000/export_csv
```

### Export με όριο (π.χ. 500 εγγραφές):
```bash
curl http://localhost:8000/export_csv?limit=500
```

## Τεχνικές Λεπτομέρειες

### Scroll API (για unlimited export)
Το OpenSearch Scroll API επιτρέπει:
- Ανάκτηση όλων των εγγραφών σε batches των 1000
- Δεν υπάρχει όριο στον συνολικό αριθμό
- Αυτόματο cleanup του scroll context

### Volume Mount
Το Docker compose έχει:
```yaml
volumes:
  - ./exports:/app/exports
```
Άρα το `/app/exports/entities.csv` στο container → `./exports/entities.csv` τοπικά.

## Rebuild & Test

Για να εφαρμόσεις τις αλλαγές:

**Windows (χρησιμοποίησε το script):**
```cmd
rebuild_orchestrator.bat
```

**Ή manual:**
```bash
docker-compose stop orchestrator
docker-compose build orchestrator
docker-compose up -d
```

Έλεγχος:
```bash
# Health check
curl http://localhost:8000/health

# Κάνε ingest μερικά URLs (αν δεν έχεις δεδομένα)
curl -X POST http://localhost:8000/ingest_urls -H "Content-Type: application/json" -d "{\"urls\": [\"https://example.com\", \"https://github.com\"]}"

# Export σε CSV (όλα τα δεδομένα)
curl http://localhost:8000/export_csv

# Τσέκαρε το αρχείο
type exports\entities.csv
```

## Troubleshooting

### Αν το CSV είναι άδειο:
1. Τσέκαρε αν έχεις δεδομένα στο OpenSearch:
   ```bash
   curl http://localhost:8000/search_hybrid -X POST -H "Content-Type: application/json" -d "{\"query\":\"*\",\"k\":10}"
   ```

2. Κάνε ingest μερικά URLs πρώτα:
   ```bash
   curl -X POST http://localhost:8000/ingest_urls -H "Content-Type: application/json" -d "{\"urls\": [\"https://example.com\"]}"
   ```

### Αν βλέπεις FileExistsError:
Τα νέα fixes το διορθώνουν αυτόματα, αλλά μπορεις να καθαρίσεις manual:
```bash
docker-compose exec orchestrator rm -f /app/exports
docker-compose restart orchestrator
```

