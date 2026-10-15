from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from auth import (
    Token,
    UserCreate,
    UserOut,
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)
from config import get_settings
import rag

settings = get_settings()

app = FastAPI(
    title="AI Regulatory Document Assistant",
    description=(
        "Session-scoped RAG for company policy Q&A. "
        "Documents stay in memory for the login session only. "
        "Author: Thalari Sony Prashanthi"
    ),
    version="2.0.0",
    contact={"name": "Thalari Sony Prashanthi"},
)


class EnsureCORS(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin") or "*"
        if request.method == "OPTIONS":
            return JSONResponse(
                content={"ok": True},
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD",
                    "Access-Control-Allow-Headers": request.headers.get(
                        "access-control-request-headers", "*"
                    ),
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = "*"
        return response


_origins = settings.origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(EnsureCORS)


class QueryIn(BaseModel):
    question: str


@app.get("/")
@app.head("/")
def root():
    return {
        "status": "ok",
        "service": "AI Regulatory Document Assistant",
        "author": "Thalari Sony Prashanthi",
        "version": "2.0.0",
        "health": "/api/health",
        "docs": "/docs",
        "storage": "session-memory-only",
        "gemini_configured": bool(settings.resolved_gemini_key()),
    }


@app.get("/api/health")
@app.head("/api/health")
def health():
    payload = {
        "status": "ok",
        "author": "Thalari Sony Prashanthi",
        "version": "2.0.0",
        "storage": "session-memory-only",
        "gemini_configured": bool(settings.resolved_gemini_key()),
        "message": "Uploaded documents are NOT persisted. Session memory only.",
    }
    payload.update(rag.gemini_status())
    return payload


@app.post("/api/auth/register", response_model=UserOut)
def register(body: UserCreate):
    return create_user(body)


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return Token(
        access_token=create_access_token(user["email"]),
        user=UserOut(email=user["email"], full_name=user["full_name"]),
    )


@app.get("/api/auth/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return user


@app.post("/api/auth/logout")
def logout(user: UserOut = Depends(get_current_user)):
    rag.clear_session(user.email)
    return {
        "message": "Logged out. Session documents wiped from memory.",
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
        return rag.add_document(user.email, file.filename or "document.txt", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}") from e


@app.get("/api/documents")
def documents(user: UserOut = Depends(get_current_user)):
    files = rag.list_documents(user.email)
    return {
        "files": files,
        "count": len(files),
        "storage": "session-memory-only",
        "notice": "Documents exist only for this login session.",
    }


@app.delete("/api/documents")
def clear_documents(user: UserOut = Depends(get_current_user)):
    rag.clear_session(user.email)
    return {"message": "Session documents cleared.", "files": []}


@app.post("/api/query")
def query(body: QueryIn, user: UserOut = Depends(get_current_user)):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    try:
        return rag.answer_query(user.email, body.question.strip())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}") from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
