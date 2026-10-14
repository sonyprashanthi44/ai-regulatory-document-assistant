# 04 — Sample Interview Questions

**Project:** AI Regulatory Document Assistant  
**Author:** Thalari Sony Prashanthi

## Product & privacy

**Q: Why not store documents in S3 or a vector database?**  
A: The product requirement is session-only processing for sensitive policies. In-memory chunks reduce retention risk and make the privacy story clear for demos and regulated pilots.

**Q: What happens on logout?**  
A: The API deletes that user’s in-memory chunk/embedding store. The UI also drops the JWT from localStorage.

## RAG

**Q: Explain your RAG pipeline.**  
A: Extract text → chunk with overlap → embed with Gemini → cosine top-k → prompt the LLM with only retrieved context and require citations.

**Q: How do you prevent hallucination?**  
A: Instruction-tuned prompt: answer only from context; admit when insufficient; return source filenames from retriever metadata.

**Q: Why cosine similarity on dense embeddings?**  
A: Simple, fast in NumPy for session-scale corpora; no infra dependency. Production might add hybrid BM25 + rerankers.

## Backend

**Q: How is auth implemented?**  
A: Register stores bcrypt password hashes in memory; login issues HS256 JWT; protected routes use `OAuth2PasswordBearer`.

**Q: What breaks in horizontal scaling?**  
A: Process-local session dicts are not shared. Sticky sessions or an external ephemeral store (Redis with TTL) would be needed—intentionally out of scope for v1 privacy/demo design.

## Frontend

**Q: How does the SPA call secured APIs?**  
A: Bearer token from login stored in localStorage and sent on each request via a small API helper.

## LLM choice

**Q: Why Gemini over OpenAI?**  
A: Single key for embeddings + generation, generous free tier for portfolio hosting, competitive quality for short compliance Q&A.

## Stretch answers

- Add OCR for scans  
- Add Redis TTL sessions  
- Add evaluation set (faithfulness / citation accuracy)  
- SSO (OIDC) for enterprise  
