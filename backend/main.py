from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from config import get_settings
from auth import (
    UserCreate,
    UserOut,
    Token,
    create_user,
    authenticate_user,
    create_access_token,
    get_current_user,
)
import rag

settings = get_settings()

app = FastAPI(
    title="AI Regulatory Document Assistant",
    description=(
        "Session-scoped RAG for company policy Q&A. "
        "Uploaded documents are held in memory for the login session only — "
        "never written to disk or a database. "
        "Author: Thalari Sony Prashanthi"
    ),
    version="1.0.0",
    contact={"name": "Thalari Sony Prashanthi"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryIn(BaseModel):
    question: str


@app.get("/")
@app.head("/")
def root():
    """Render health checks probe HEAD/GET / and require HTTP 200."""
    return {
        "status": "ok",
        "service": "AI Regulatory Document Assistant",
        "author": "Thalari Sony Prashanthi",
        "health": "/api/health",
        "docs": "/docs",
        "storage": "session-memory-only",
    }


@app.get("/api/health")
@app.head("/api/health")
def health():
    return {
        "status": "ok",
        "author": "Thalari Sony Prashanthi",
        "storage": "session-memory-only",
        "message": "Uploaded documents are NOT persisted. They exist only for the active login session.",
    }


@app.post("/api/auth/register", response_model=UserOut)
def register(body: UserCreate):
    return create_user(body)


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(user["email"])
    return Token(
        access_token=token,
        user=UserOut(email=user["email"], full_name=user["full_name"]),
    )


@app.get("/api/auth/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return user


@app.post("/api/auth/logout")
def logout(user: UserOut = Depends(get_current_user)):
    rag.clear_session(user.email)
    return {
        "message": "Logged out. All session documents and embeddings were wiped from memory.",
        "storage": "session-memory-only",
    }


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: UserOut = Depends(get_current_user),
):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 8MB)")
    try:
        result = rag.add_document(user.email, file.filename or "document.txt", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}")
    return result


@app.get("/api/documents")
def documents(user: UserOut = Depends(get_current_user)):
    files = rag.list_documents(user.email)
    return {
        "files": files,
        "count": len(files),
        "storage": "session-memory-only",
        "notice": "Documents exist only for this login session and are never stored on disk or in a database.",
    }


@app.delete("/api/documents")
def clear_documents(user: UserOut = Depends(get_current_user)):
    rag.clear_session(user.email)
    return {"message": "Session documents cleared from memory.", "files": []}


@app.post("/api/query")
def query(body: QueryIn, user: UserOut = Depends(get_current_user)):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    try:
        return rag.answer_query(user.email, body.question.strip())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
