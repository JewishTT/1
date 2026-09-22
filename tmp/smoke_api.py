"""Smoke-test the exact APIs of bm25s / tantivy / duckdb before wiring them in."""

import bm25s

retriever = bm25s.BM25(k1=1.2, b=0.75, method="lucene")
corpus_tokens = [
    ["sanctions", "list", "assets", "offshore"],
    ["sanctions", "are", "garden", "vegetables"],
]
doc_ids = ["obs:o1", "obs:o2"]
retriever.index(corpus_tokens, show_progress=False)
res = retriever.retrieve(
    [["sanctions", "assets"]],
    corpus=doc_ids,
    k=2,
    return_as="tuple",
    show_progress=False,
)
print("bm25s docs:", type(res.documents), res.documents)
print("bm25s scores:", type(res.scores), res.scores)
print("bm25s vocab has:", "vocab_dict" in retriever.__dict__ or hasattr(retriever, "vocab_dict"))

# OOV token behaviour (a query term not in the index)
try:
    res2 = retriever.retrieve(
        [["zzz_unknown_token"]], corpus=doc_ids, k=2, return_as="tuple", show_progress=False
    )
    print("bm25s OOV ok:", res2.documents, res2.scores)
except Exception as exc:  # noqa: BLE001
    print("bm25s OOV raised:", type(exc).__name__, exc)

# Empty-query behaviour
try:
    res3 = retriever.retrieve([[]], corpus=doc_ids, k=2, return_as="tuple", show_progress=False)
    print("bm25s empty ok:", res3.documents, res3.scores)
except Exception as exc:  # noqa: BLE001
    print("bm25s empty raised:", type(exc).__name__, exc)

import tantivy

sb = tantivy.SchemaBuilder()
sb.add_text_field("doc_id", stored=True, tokenizer_name="raw")
sb.add_text_field("kind", stored=True, tokenizer_name="raw")
sb.add_text_field("tenant_id", stored=True, tokenizer_name="raw")
sb.add_text_field("text", stored=True, tokenizer_name="default")
schema = sb.build()
index = tantivy.Index(schema)
writer = index.writer()
writer.add_document(
    tantivy.Document(doc_id="d1", kind="documents", tenant_id="t1", text="offshore assets freeze")
)
writer.add_document(
    tantivy.Document(doc_id="d2", kind="documents", tenant_id="t2", text="garden vegetables")
)
writer.commit()
index.reload()
searcher = index.searcher()
q = index.parse_query("offshore", ["text"])
term_kind = tantivy.Query.term_query(schema, "kind", "documents")
bool_q = tantivy.Query.boolean_query([(tantivy.Occur.Must, q), (tantivy.Occur.Must, term_kind)])
result = searcher.search(bool_q, 10)
print("tantivy hits:", [(round(s, 3), searcher.doc(a).to_dict()) for s, a in result.hits])

import duckdb

con = duckdb.connect(":memory:")
con.execute("CREATE TABLE obs(observation_id TEXT, tenant_id TEXT, content_type TEXT)")
con.executemany("INSERT INTO obs VALUES (?,?,?)", [("o1", "t1", "text/html"), ("o2", "t1", "application/json")])
print("duckdb:", con.execute("SELECT content_type, count(*) FROM obs GROUP BY 1 ORDER BY 1").fetchall())
con.close()

import certstream

print("certstream module:", certstream.CERTSTREAM_URL if hasattr(certstream, "CERTSTREAM_URL") else dir(certstream)[:10])
print("SMOKE OK")
