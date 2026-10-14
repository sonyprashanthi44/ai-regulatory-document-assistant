# 01 — Project Overview & Real-World Use Case

**Project:** AI Regulatory Document Assistant  
**Author:** Thalari Sony Prashanthi

## Problem

Compliance, legal, and operations teams spend hours searching lengthy policy PDFs for answers such as retention periods, approval paths, or incident response steps. Keyword search misses context; sharing full policies with external AI tools risks data leakage.

## Solution

A secure web application where authenticated users:

1. Upload policy documents for the **current login session only**
2. Ask natural-language questions
3. Receive answers grounded in those documents via **RAG**
4. See source filenames for auditability

Documents are **never written to disk or a database**. They exist only in server memory until logout, clear, or process restart.

## Real-world use cases

- **HR / People ops:** “What is the notice period for resignations?”
- **InfoSec:** “Who must be notified after a suspected data breach?”
- **Finance:** “What is the approval limit for vendor invoices?”
- **Consulting demos:** Show enterprise RAG without retaining client files

## Why session-only storage matters

Regulated industries (banking, healthcare, government contractors) often cannot leave policy corpora on third-party disks. Session-memory RAG lets stakeholders evaluate AI assistance while minimizing retention risk—ideal for demos, pilots, and portfolio showcases.

## Target users

- Compliance analysts
- Internal audit
- Security champions
- Engineering managers evaluating RAG patterns

## Success criteria

- Authenticated access only for document/query APIs
- Correct retrieval from uploaded text
- Clear UX disclosure that files are not persisted
- Deployable portfolio demo with public GitHub repo

## Scope (portfolio v1)

In scope: JWT auth, upload, in-memory RAG, Gemini generation, React UI, docs.  
Out of scope: multi-tenant DB, SSO, long-term vector DB, admin console, OCR for scanned PDFs.
