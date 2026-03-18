# dg-form — Disc Golf Form Critique App

## Overview

A stateless web application that accepts a user-uploaded disc golf video, automatically
detects and suggests the throw segment, lets the user fine-tune the trim and supply context
about the throw, then submits the clipped video to an OpenAI model for structured form
critique delivered as both annotated video and human-readable text feedback. During
processing the frontend displays a live stage-by-stage progress feed so users understand
what the system is doing rather than watching a blank spinner.

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
│  │  • Shot context form (throw type + camera)   │   │
│  │  • Analysis progress feed (SSE live log)     │   │
│  │  • Results view (text + annotated video)     │   │
│  └───────────────┬──────────────────────────────┘   │
└──────────────────┼──────────────────────────────────┘
                   │ REST / multipart / SSE
┌──────────────────▼──────────────────────────────────┐
│  FastAPI (Python)                                   │
│                                                     │
│  POST /upload      → returns suggested trim range   │
│  POST /analyze     → accepts trim + shot context    │
│                      streams SSE progress events    │
│                      final event: critique+clip URL │
│  GET  /clip/{id}   → streams the annotated clip     │
│                                                     │
│  ┌────────────────────────────────────────────────┐ │
│  │  Video Pipeline                                │ │
│  │  1. Receive upload, save to temp storage       │ │
│  │  2. MediaPipe Pose — detect motion onset/end   │ │
│  │  3. Return suggested [start_ms, end_ms]        │ │
│  │  4. (After user confirms) clip with FFmpeg ──► SSE: clipping   │ │
│  │  5. Extract N key frames (OpenCV)          ──► SSE: extracting │ │
│  │  6. Send frames + context → OpenAI GPT-4o  ──► SSE: analyzing  │ │
│  │  7. Parse structured critique response     ──► SSE: annotating │ │
│  │  8. Annotate frames with critique overlays ──► SSE: assembling │ │
│  │  9. Reassemble annotated clip (FFmpeg)     ──► SSE: complete   │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## User Flow

1. **Upload** — User selects a video file. Accepted formats: MP4, MOV, 3GP, WebM (covers
   default formats from iOS and Android smartphones). Max size: **200 MB**.
2. **Auto-detect** — Backend runs pose/motion analysis and returns a suggested `[start, end]`
   range marking the throw segment.
3. **Trim + Context** — Frontend shows the video with the suggested trim overlaid as a range
   slider. The same screen also presents a **Shot Context** form with two required fields:
   - **Throw type**: Backhand | Forehand (side throw)
   - **Camera perspective**: Front-facing | Back-facing | Side-facing (toward thrower) |
     Side-facing (away from thrower)

   The trim and context selections are collected together; the user confirms both before
   proceeding. Low-confidence auto-trim warnings remain visible to prompt manual adjustment.

4. **Analyze** — User clicks _Analyze Throw_. The frontend connects to the `POST /analyze`
   SSE stream, which emits live progress events as each pipeline stage completes. The UI
   displays a **live processing feed** with the current stage name, a progress indicator,
   and a running log of completed steps (see Live Processing Feed section).

5. **Results** — User sees:
   - **Annotated video**: original clip with per-frame text overlays (e.g. "grip tension",
     "elbow drop") at the relevant moments.
   - **Text critique**: structured breakdown including a throw-type confirmation and
     camera-aware observations (see Output Format below).

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
    "suggested_trim": { "start_ms": 1200, "end_ms": 4300 },
    "low_confidence": false,
    "detected_throw_type": "backhand | forehand | unknown",
    "throw_type_confidence": 0.87
  }
  ```
  `detected_throw_type` is the result of the auto-classification pipeline (see
  [Auto throw-type detection](#auto-throw-type-detection)). `throw_type_confidence`
  is a float in `[0.0, 1.0]`; values below **0.70** cause `detected_throw_type` to be
  set to `"unknown"` so the frontend leaves the field unselected rather than surfacing a
  low-confidence guess.

### `POST /analyze`
- **Content-Type**: `application/json`
- **Body**:
  ```json
  {
    "upload_id": "uuid",
    "trim": { "start_ms": 1200, "end_ms": 4300 },
    "throw_type": "backhand | forehand | unknown",
    "camera_perspective": "front | back | side_facing | side_away | unknown"
  }
  ```
  `throw_type` and `camera_perspective` are both **required** fields. The frontend
  always sends an explicit value; if the user skipped the form for any reason both
  default to `"unknown"` so the prompt degrades gracefully.

- **Response**: `Content-Type: text/event-stream` (Server-Sent Events)

  The endpoint returns an SSE stream. Each event is a JSON object on the `data:` line.
  Two event types are used:

  **`progress` events** — emitted at the start of each pipeline stage:
  ```
  event: progress
  data: {"stage": "clipping",    "message": "Trimming video to selected range…",   "step": 1, "total_steps": 5}

  event: progress
  data: {"stage": "extracting",  "message": "Extracting key frames…",              "step": 2, "total_steps": 5}

  event: progress
  data: {"stage": "analyzing",   "message": "Sending frames to AI coach…",         "step": 3, "total_steps": 5}

  event: progress
  data: {"stage": "annotating",  "message": "Annotating frames with critique…",    "step": 4, "total_steps": 5}

  event: progress
  data: {"stage": "assembling",  "message": "Building annotated clip…",            "step": 5, "total_steps": 5}
  ```

  **`complete` event** — final event, contains the full result:
  ```
  event: complete
  data: {"clip_id": "uuid", "critique": { ... }}
  ```

  **`error` event** — emitted if any stage fails (stream then closes):
  ```
  event: error
  data: {"message": "Analysis failed. Please try again."}
  ```

  The frontend reads the stream using `fetch()` with `ReadableStream` (not `EventSource`,
  which only supports `GET`). On receipt of `complete` or `error` the frontend closes
  the reader and transitions state accordingly.

### `GET /clip/{clip_id}`
- Streams the annotated MP4 clip (Content-Type: `video/mp4`).
- The file is deleted from tmpfs via a `BackgroundTask` after the response is fully streamed.

### `GET /health`
- Liveness probe for container orchestration.

---

## Video Processing Detail

### Auto-detect throw segment
Use **MediaPipe Pose** to track wrist/shoulder velocity frame-by-frame. The throw segment
is identified as the window with peak angular velocity of the throwing arm, padded by
~0.5 s on each side. Fallback: if pose confidence is low, return the middle 40% of the
video and flag `"low_confidence": true` so the UI can prompt the user to trim manually.

### Auto throw-type detection
Immediately after the throw segment boundaries are established, a second MediaPipe Pose
pass over the detected throw window classifies the throw type before the upload response
is returned. No extra round-trip is needed; the result is included in the `/upload`
response alongside `suggested_trim`.

**Algorithm**

1. For each frame in the detected throw window, read the `x`-coordinate of the throwing
   wrist (dominant hand is inferred from whichever wrist has higher frame-to-frame
   velocity).
2. Measure the **lateral displacement vector** of the wrist relative to the mid-shoulder
   line (midpoint of left and right shoulder landmarks, projected onto the horizontal axis
   in normalised coordinates).
3. Compute the **net cross-body travel**: the signed sum of horizontal wrist movement
   across the throw window.
   - **Backhand**: wrist starts near the non-dominant hip and crosses the body toward
     the opposite side — net travel is strongly **toward** the mid-shoulder line from
     outside it (large positive cross-body delta).
   - **Forehand / flick**: wrist starts close to the dominant hip and swings outward in
     a pendulum arc — net travel is **away** from the mid-shoulder line toward the
     throwing side (large negative cross-body delta).
4. Apply a signed threshold: if `|delta| ≥ 0.25` (normalised units, empirically tuned),
   classify as backhand or forehand. Confidence is derived from the ratio of
   `|delta| / expected_max_delta` clamped to `[0.0, 1.0]`.
5. If fewer than 10 high-confidence pose frames are available in the window, or if
   `confidence < 0.70`, set `detected_throw_type` to `"unknown"` and
   `throw_type_confidence` to the raw value (so the frontend can optionally surface a
   "low confidence" hint).

**Fallbacks**

| Condition | Outcome |
|---|---|
| Pose confidence low throughout clip | `unknown`, raw confidence returned |
| Only one wrist detected | Use that wrist; mark confidence ×0.8 |
| Clip shorter than 10 frames | `unknown` |

This runs synchronously inside the `/upload` handler (same `asyncio.to_thread` task as
pose-based trim detection), adding negligible latency.

### Frame extraction
Extract ~8–12 evenly-spaced frames from the confirmed clip. Fewer frames = lower API cost;
more frames = better temporal coverage. Target one frame per ~200 ms of clip.

### OpenAI prompt strategy
Send frames as a sequence of images in a single `gpt-4o` message. Include a structured
system prompt:
- Describe the sport context (disc golf)
- Include the **throw type** provided by the user (`backhand` / `forehand` / `unknown`);
  when known, the prompt requests throw-type-specific form analysis
- Include the **camera perspective** (`front` / `back` / `side_facing` / `side_away` /
  `unknown`); the model uses this to know which body parts and angles are visible and to
  calibrate which cues are reliable vs. occluded
- Ask for JSON output matching the `critique` schema above
- Reference standard form phases: grip & setup, reach-back, pull-through, release,
  follow-through

**Camera perspective guidance injected into the prompt:**

| Perspective | Model is told to focus on |
|---|---|
| `front` | chest/hip rotation, elbow path, disc plane at release |
| `back` | reach-back depth, X-step footwork, follow-through direction |
| `side_facing` | arm extension, timing of hip vs. shoulder rotation, flight angle |
| `side_away` | same as `side_facing` with camera-left/right flipped; note limb occlusion |
| `unknown` | general analysis; model infers what is visible |

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
  "camera_perspective": "front | back | side_facing | side_away | unknown",
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

`camera_perspective` in the response is the model's confirmation of the perspective it
analysed (echo of user input, or its own inference when `unknown` was supplied). This
allows the frontend to display a context summary alongside the critique.

---

## Shot Context

Before submitting the clip for analysis the user fills in two fields presented in the
**TrimEditor** screen alongside the range sliders:

### Throw Type
| Value | Display label | Notes |
|---|---|---|
| `backhand` | Backhand | Standard RHBH/LHBH drives and approaches |
| `forehand` | Forehand / Side throw | Sometimes called a flick or side-arm |
| `unknown` | I'm not sure | Model will attempt to infer; quality of feedback may be lower |

### Camera Perspective
| Value | Display label | What the camera sees |
|---|---|---|
| `front` | Front-facing | Camera faces the thrower's chest; throw goes away from camera |
| `back` | Back-facing | Camera is behind the thrower; throw goes toward camera |
| `side_facing` | Side — facing camera | Thrower is side-on, releasing toward the camera |
| `side_away` | Side — facing away | Thrower is side-on, releasing away from the camera |
| `unknown` | Unknown / mixed | Camera angle is unclear or changes during the clip |

### UI behaviour
- Both fields are **required** before the Analyze button is enabled.
- **Throw type auto-population**: if `detected_throw_type` in the upload response is not
  `"unknown"` (i.e. `throw_type_confidence ≥ 0.70`), the throw type selector is
  pre-populated with the detected value and a small **"Auto-detected"** badge is shown
  inline. The user can change the selection at any time before clicking Analyze.
- If `detected_throw_type` is `"unknown"`, the throw type selector starts unselected as
  before, and an optional low-confidence hint may be displayed if `throw_type_confidence`
  is present but below threshold.
- Default selection for camera perspective: none (user must pick).
- The fields appear below the trim sliders and above the action buttons in `TrimEditor`.
- On small screens the two selectors stack vertically.

### Pydantic schema additions
```python
class ThrowType(str, Enum):
    backhand = "backhand"
    forehand = "forehand"
    unknown  = "unknown"

class CameraPerspective(str, Enum):
    front        = "front"
    back         = "back"
    side_facing  = "side_facing"
    side_away    = "side_away"
    unknown      = "unknown"

class UploadResponse(BaseModel):
    upload_id:              str
    duration_ms:            int
    suggested_trim:         TrimRange
    low_confidence:         bool
    detected_throw_type:    ThrowType
    throw_type_confidence:  float          # [0.0, 1.0]

class AnalyzeRequest(BaseModel):
    upload_id:          str
    trim:               TrimRange
    throw_type:         ThrowType
    camera_perspective: CameraPerspective
```

`CritiqueResponse` also gains `camera_perspective: CameraPerspective` as a confirmation
field echoed back from the model's analysis.

---

## Live Processing Feed

### Motivation
The analyze pipeline runs for 15–120 seconds depending on clip length and OpenAI latency.
Silently waiting with a spinner provides no feedback and makes the app feel broken. A
live stage log tells users exactly what is happening and gives them confidence the system
is progressing.

### Transport: Server-Sent Events (SSE)
`POST /analyze` returns `Content-Type: text/event-stream` instead of a plain JSON
response. FastAPI's `StreamingResponse` with an async generator is used on the backend.
Each pipeline stage runs inside `asyncio.to_thread`; an `asyncio.Queue` is used to pass
progress messages from the thread pool back to the async generator.

```
Frontend                              Backend (FastAPI)
   │                                        │
   │── POST /analyze ─────────────────────►│
   │                                        │── emit: progress{clipping}
   │◄── event: progress{clipping} ─────────│
   │                                        │   [ffmpeg trim runs…]
   │◄── event: progress{extracting} ───────│
   │                                        │   [OpenCV extraction…]
   │◄── event: progress{analyzing} ────────│
   │                                        │   [OpenAI API call…]
   │◄── event: progress{annotating} ───────│
   │                                        │   [OpenCV annotation…]
   │◄── event: progress{assembling} ───────│
   │                                        │   [ffmpeg re-encode…]
   │◄── event: complete{clip_id, critique}─│
   │                                        │ [stream closes]
```

### Backend implementation
- `analyze_video` is an async generator function wrapped in `StreamingResponse`.
- An `asyncio.Queue[str | None]` is created per request. Each stage sends a
  pre-serialised SSE string into the queue after the `asyncio.to_thread` call completes.
- The generator `await queue.get()`s until it receives `None` (sentinel) or an error
  string.
- `finally` cleanup runs normally; the SSE stream closing signals the client that no more
  events are coming regardless of success or failure.

### Frontend implementation
- `client.ts` exports `analyzeVideoStream(request, onProgress, onComplete, onError)`
  which uses `fetch()` + `response.body.getReader()` + a lightweight SSE line parser.
- `TrimEditor.tsx` calls `analyzeVideoStream` instead of `analyzeVideo`. When the call
  begins it transitions to an in-component `"analyzing"` sub-state that renders the
  `AnalysisProgress` component.
- `AnalysisProgress.tsx` (new component) renders the live log:
  - A vertical list of the 5 pipeline stages
  - Each stage shows: ✓ (complete, grey), ⟳ (in-progress, animated, blue), or an empty
    circle (pending, grey)
  - A one-line status message below the list (the `message` string from the current event)
  - Accessible: `role="status"` container, `aria-live="polite"`, each completed item
    announced via `aria-label`

### AnalysisProgress stage definitions (frontend)
```typescript
const STAGES = [
  { key: 'clipping',   label: 'Trimming clip'            },
  { key: 'extracting', label: 'Extracting frames'         },
  { key: 'analyzing',  label: 'AI form analysis'          },
  { key: 'annotating', label: 'Annotating frames'         },
  { key: 'assembling', label: 'Building annotated clip'   },
] as const;
```

---

## Project Structure (proposed)

```
dg-form/
├── api/                        # FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── upload.py
│   │   └── analyze.py          # returns StreamingResponse (SSE)
│   ├── services/
│   │   ├── video_pipeline.py   # clip, extract frames, assemble clip
│   │   ├── pose_detection.py   # MediaPipe auto-trim
│   │   ├── openai_client.py    # GPT-4o integration (uses throw_type + camera_perspective)
│   │   └── annotation.py      # OpenCV overlays
│   ├── models/
│   │   └── schemas.py          # ThrowType, CameraPerspective enums; updated AnalyzeRequest
│   └── Dockerfile
├── web/                        # React + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoUpload.tsx
│   │   │   ├── TrimEditor.tsx          # + ShotContext fields + analyzeVideoStream
│   │   │   ├── AnalysisProgress.tsx    # NEW — live SSE stage feed
│   │   │   └── CritiqueResults.tsx
│   │   ├── api/
│   │   │   └── client.ts               # analyzeVideoStream() replaces analyzeVideo()
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
- **Auto throw-type detection**: implemented — see [Auto throw-type detection](#auto-throw-type-detection).
  Future extension: more granular classification (roller, tomahawk, hyzer vs. anhyzer,
  putting style) once a larger set of labelled poses is available for threshold tuning.
- **WebSocket upgrade**: The current SSE transport is one-way (server → client). If
  interactive mid-analysis controls are added (e.g. cancel button, re-trim), upgrade the
  transport to WebSocket (`/ws/analyze`).
- **Batch / async processing**: Move the analyze job to a background task queue (Celery /
  ARQ) for very long videos; the SSE stream would then poll job status rather than holding
  the HTTP connection open for the full duration.
- **Mobile upload**: The React frontend is responsive by design; a PWA wrapper could enable
  direct camera capture on mobile.
- **Expanded annotation**: Beyond text overlays, future iterations could draw pose skeleton
  highlights, directional arrows, or bounding boxes on key frames using OpenCV drawing
  primitives.
