# dg-form — Workspace Instructions

This is a disc golf throw form critique application. All agents working in this repo must understand the following context before writing any code.

## Project Purpose
Users upload smartphone video of a disc golf throw. The app auto-detects the throw segment using MediaPipe pose detection, lets the user fine-tune the trim, then sends extracted frames to GPT-4o Vision for structured form critique. Output is a text critique and an annotated video clip.

## Stack
- **Backend**: Python 3.12 + FastAPI (`/api`)
- **Video processing**: OpenCV, MediaPipe, ffmpeg-python
- **AI**: OpenAI GPT-4o Vision
- **Frontend**: React 18 + Vite + TypeScript (`/web`)
- **Infra**: Docker Compose (two services: `api`, `web`)

## Project Layout
```
dg-form/
├── .github/
│   ├── agents/         # Custom Copilot agents
│   ├── copilot-instructions.md
│   └── prompts/
├── api/
│   ├── main.py
│   ├── routers/        # upload.py, analyze.py
│   ├── services/       # video_pipeline.py, pose_detection.py, openai_client.py, annotation.py
│   ├── models/         # Pydantic schemas
│   └── Dockerfile
├── web/
│   ├── src/
│   │   ├── components/ # VideoUpload, TrimEditor, CritiqueResults
│   │   └── App.tsx
│   └── Dockerfile
├── docker-compose.yml
├── SPEC.md
└── README.md
```

## Non-Negotiable Rules
- **No video retention**: All uploaded and processed video files MUST be deleted after the analyze response is delivered. Use `finally` blocks to guarantee cleanup.
- **Accepted video formats**: MP4, MOV, 3GP, WebM only. Validate MIME type on upload.
- **Max upload size**: 200 MB.
- **Stateless**: No database, no user sessions, no persistent storage in the MVP.
- **Security**: Never log video file contents. Sanitize all filenames on upload (use `uuid` for temp paths, never user-provided names).
- **Pydantic models** required for all request/response shapes.
- **Async** FastAPI handlers throughout — no blocking I/O on the event loop.

## Critique Schema
All OpenAI responses must be validated against this structure:
```json
{
  "overall_score": "string",
  "summary": "string",
  "throw_type": "backhand | forehand | unknown",
  "phases": [
    {
      "name": "string",
      "timestamp_ms": "integer",
      "observations": ["string"],
      "recommendations": ["string"]
    }
  ],
  "key_focus": "string"
}
```

## API Endpoints
- `POST /upload` — receive video, run auto-trim detection, return `upload_id` + `suggested_trim`
- `POST /analyze` — accept `upload_id` + confirmed trim, return `clip_id` + `critique`
- `GET /clip/{clip_id}` — stream annotated MP4
- `GET /health` — liveness probe

## Code Style
- Python: follow PEP 8, use type hints everywhere, prefer `pathlib.Path` over `os.path`
- TypeScript: strict mode, functional components, no `any`
- Keep functions small and single-purpose
- No print statements — use Python `logging` module
