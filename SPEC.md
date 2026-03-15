# dg-form — Disc Golf Form Critique App

## Overview

A stateless web application that accepts a user-uploaded disc golf video, automatically
detects and suggests the throw segment, lets the user fine-tune the trim, then submits the
clipped video to an OpenAI model for structured form critique delivered as both annotated
video and human-readable text feedback.

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| **Backend API** | Python 3.12 + FastAPI | Async, container-native, OpenAPI docs out of the box |
| **Video processing** | OpenCV + MediaPipe + FFmpeg (via `ffmpeg-python`) | Best-in-class pose detection, frame manipulation, clip assembly |
| **AI critique** | OpenAI GPT-4o (Vision) | Accepts sequences of extracted frames; understands spatial/motion context |
| **Frontend** | React + Vite (TypeScript) | Video trim UI requires rich JS interaction; Vite keeps the build simple |
| **Containerization** | Docker Compose (two services: `api`, `web`) | Easy local dev; maps directly onto a single-host or simple cloud deployment |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser                                            │
│  ┌──────────────────────────────────────────────┐   │
│  │  React SPA                                   │   │
│  │  • Video upload widget                       │   │
│  │  • Trim editor  (suggested range editable)   │   │
│  │  • Results view (text + annotated video)     │   │
│  └───────────────┬──────────────────────────────┘   │
└──────────────────┼──────────────────────────────────┘
                   │ REST / multipart
┌──────────────────▼──────────────────────────────────┐
│  FastAPI (Python)                                   │
│                                                     │
│  POST /upload      → returns suggested trim range   │
│  POST /analyze     → accepts confirmed trim range   │
│                      returns critique + clip URL    │
│  GET  /clip/{id}   → streams the annotated clip     │
│                                                     │
│  ┌────────────────────────────────────────────────┐ │
│  │  Video Pipeline                                │ │
│  │  1. Receive upload, save to temp storage       │ │
│  │  2. MediaPipe Pose — detect motion onset/end   │ │
│  │  3. Return suggested [start_ms, end_ms]        │ │
│  │  4. (After user confirms) clip with FFmpeg     │ │
│  │  5. Extract N key frames (OpenCV)              │ │
│  │  6. Send frames + prompt → OpenAI GPT-4o       │ │
│  │  7. Parse structured critique response        │ │
│  │  8. Annotate frames with critique overlays    │ │
│  │  9. Reassemble annotated clip (FFmpeg)         │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## User Flow

1. **Upload** — User selects a video file. Accepted formats: MP4, MOV, 3GP, WebM (covers default
   formats from iOS and Android smartphones). Max size: **200 MB**.
2. **Auto-detect** — Backend runs pose/motion analysis and returns a suggested `[start, end]`
   range marking the throw segment.
3. **Trim review** — Frontend shows the video with the suggested trim overlaid as a range
   slider. User can adjust start/end and preview before confirming.
4. **Analyze** — User submits the confirmed clip. Backend clips the video, extracts frames,
   and calls OpenAI.
5. **Results** — User sees:
   - **Annotated video**: original clip with per-frame text overlays (e.g. "grip tension",
     "elbow drop") at the relevant moments.
   - **Text critique**: structured breakdown (see Output Format below).
6. **Reset** — User can start over with a new video (stateless; no persistence).

> **File lifecycle**: all uploaded and processed video files are deleted from the server
> immediately after the analyze response is successfully delivered to the client. No video
> data is retained after processing completes.

---

## API Endpoints

### `POST /upload`
- **Body**: `multipart/form-data` with `video` file field
- **Accepted formats**: `video/mp4`, `video/quicktime` (MOV), `video/3gpp` (3GP), `video/webm`
- **Max size**: 200 MB
- **Response**:
  ```json
  {
    "upload_id": "uuid",
    "duration_ms": 8400,
    "suggested_trim": { "start_ms": 1200, "end_ms": 4300 }
  }
  ```

### `POST /analyze`
- **Body**:
  ```json
  {
    "upload_id": "uuid",
    "trim": { "start_ms": 1200, "end_ms": 4300 }
  }
  ```
- **Response**:
  ```json
  {
    "clip_id": "uuid",
    "critique": {
      "overall_score": "7/10",
      "summary": "...",
      "phases": [
        {
          "name": "Grip & Setup",
          "timestamp_ms": 1200,
          "observations": ["..."],
          "recommendations": ["..."]
        }
      ]
    }
  }
  ```

### `GET /clip/{clip_id}`
- Streams the annotated MP4 clip (Content-Type: `video/mp4`).

### `GET /health`
- Liveness probe for container orchestration.

---

## Video Processing Detail

### Auto-detect throw segment
Use **MediaPipe Pose** to track wrist/shoulder velocity frame-by-frame. The throw segment
is identified as the window with peak angular velocity of the throwing arm, padded by
~0.5 s on each side. Fallback: if pose confidence is low, return the middle 40% of the
video and flag `"low_confidence": true` so the UI can prompt the user to trim manually.

### Frame extraction
Extract ~8–12 evenly-spaced frames from the confirmed clip. Fewer frames = lower API cost;
more frames = better temporal coverage. Target one frame per ~200 ms of clip.

### OpenAI prompt strategy
Send frames as a sequence of images in a single `gpt-4o` message. Include a structured
system prompt:
- Describe the sport context (disc golf, backhand/forehand throw)
- Ask for JSON output matching the `critique` schema above
- Reference standard form phases: grip & setup, reach-back, pull-through, release, follow-through

### Frame annotation
After receiving the critique, use OpenCV to draw **simple text overlays** on the relevant
frames at the timestamps provided (phase name + key observation as a caption), then
reassemble with FFmpeg into the final annotated clip. Annotation style may be extended in
future iterations (e.g. skeleton highlights, arrows, bounding boxes).

---

## Output Format (Critique Schema)

```json
{
  "overall_score": "string (e.g. 7/10)",
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
  "key_focus": "string (single most impactful improvement)"
}
```

---

## Project Structure (proposed)

```
dg-form/
├── api/                        # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── upload.py
│   │   └── analyze.py
│   ├── services/
│   │   ├── video_pipeline.py   # clip, extract frames
│   │   ├── pose_detection.py   # MediaPipe auto-trim
│   │   ├── openai_client.py    # GPT-4o integration
│   │   └── annotation.py      # OpenCV overlays
│   ├── models/                 # Pydantic schemas
│   └── Dockerfile
├── web/                        # React + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoUpload.tsx
│   │   │   ├── TrimEditor.tsx
│   │   │   └── CritiqueResults.tsx
│   │   └── App.tsx
│   └── Dockerfile
├── docker-compose.yml
└── SPEC.md
```

---

## Container Setup

```yaml
# docker-compose.yml (sketch)
services:
  api:
    build: ./api
    ports: ["8000:8000"]
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    tmpfs:
      - /tmp/uploads       # stateless; files live only for request lifetime

  web:
    build: ./web
    ports: ["5173:80"]
    depends_on: [api]
```

Temp video files are stored in an in-container `/tmp` directory. All source uploads and
processed clips are **deleted immediately after the analyze response is delivered**
(confirmed via a `finally` block or background cleanup task). No external storage required
for the stateless MVP.

---

## Future Considerations

- **Authentication**: OIDC via an identity provider (Auth0, Azure AD, Keycloak). FastAPI has
  first-class support via `python-jose` / `fastapi-users`. The stateless API design means
  adding auth is purely additive — attach a `Depends(get_current_user)` guard and a user
  context to the analyze endpoint.
- **History / persistence**: Swap the in-memory temp store for blob storage (S3/Azure Blob)
  keyed by user ID once accounts are added.
- **Throw type detection**: Auto-classify backhand vs. forehand from pose data to improve
  the OpenAI prompt and enable type-specific scoring rubrics.
- **Batch / async processing**: Move the analyze job to a background task queue (Celery /
  ARQ) for longer videos; poll or use WebSocket for status updates.
- **Mobile upload**: The React frontend is responsive by design; a PWA wrapper could enable
  direct camera capture on mobile.
