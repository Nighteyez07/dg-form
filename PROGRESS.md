# dg-form — Implementation Progress

Tracks every spec feature against its current implementation status.
Update this file whenever a gap is closed or a new feature is added.

**Legend**: ✅ Implemented · ⚠️ Partial · ❌ Missing

---

## Backend

### Schemas (`api/models/schemas.py`)

| Feature | Status | Notes |
|---|---|---|
| `ThrowType` enum (`backhand \| forehand \| unknown`) | ✅ | |
| `CameraPerspective` enum (5 values) | ✅ | |
| `TrimRange` model | ✅ | |
| `UploadResponse` with `detected_throw_type` + `throw_type_confidence` | ✅ | Added alongside pose detection implementation |
| `AnalyzeRequest` with `throw_type` + `camera_perspective` | ✅ | |
| `CritiqueResponse` with `camera_perspective` confirmation field | ✅ | |
| `ProgressEvent` / `CompleteEvent` / `ErrorEvent` SSE schemas | ✅ | |

### Upload Router (`api/routers/upload.py`)

| Feature | Status | Notes |
|---|---|---|
| Multipart video upload | ✅ | |
| MIME-type + magic-byte validation | ✅ | |
| 200 MB size cap | ✅ | |
| UUID temp paths (no user-supplied filenames) | ✅ | |
| Calls pose detection for auto-trim | ✅ | |
| Returns `detected_throw_type` + `throw_type_confidence` | ✅ | |
| Temp file eviction task | ✅ | |

### Analyze Router (`api/routers/analyze.py`)

| Feature | Status | Notes |
|---|---|---|
| SSE `StreamingResponse` (`text/event-stream`) | ✅ | |
| 5-stage pipeline: clipping → extracting → analyzing → annotating → assembling | ✅ | |
| `throw_type` + `camera_perspective` forwarded to OpenAI client | ✅ | |
| `progress` events with `stage`, `message`, `step`, `total_steps` | ✅ | |
| `complete` event with `clip_id` + `critique` | ✅ | |
| `error` event on pipeline failure | ✅ | |
| `GET /clip/{clip_id}` — streams annotated MP4 | ✅ | |
| Clip file deleted via `BackgroundTask` after stream | ✅ | |
| Full `finally` cleanup (upload, raw clip, annotated clip) | ✅ | |
| `GET /health` liveness probe | ✅ | |

### Pose Detection (`api/services/pose_detection.py`)

| Feature | Status | Notes |
|---|---|---|
| **Auto-trim segment detection** (motion energy / wrist velocity peaks) | ✅ | `_detect_trim_window`: smoothed wrist-velocity signal, peak expansion, ±500 ms pad, middle-40% fallback |
| **Auto throw-type detection** (lateral displacement algorithm) | ✅ | `_classify_throw_type`: net cross-body delta, dominant-wrist inference, one-wrist penalty, confidence thresholding |

### Video Pipeline (`api/services/video_pipeline.py`)

| Feature | Status | Notes |
|---|---|---|
| `clip_video` — FFmpeg trim to confirmed range | ✅ | |
| `extract_frames` — OpenCV, ~1 frame/200 ms, max 12 frames | ✅ | |
| `assemble_annotated_clip` — FFmpeg `image2pipe` re-encode | ✅ | |

### OpenAI Client (`api/services/openai_client.py`)

| Feature | Status | Notes |
|---|---|---|
| GPT-4o Vision multi-frame message | ✅ | |
| Throw-type-specific prompt injection | ✅ | |
| Camera-perspective-specific guidance (5 distinct strings) | ✅ | |
| Structured JSON output validated against `CritiqueResponse` | ✅ | |
| Input sanitization (valid-set guard on both hint fields) | ✅ | |

### Annotation (`api/services/annotation.py`)

| Feature | Status | Notes |
|---|---|---|
| `annotate_frame` — OpenCV text overlay with drop-shadow | ✅ | |

---

## Frontend

### API Client (`web/src/api/client.ts`)

| Feature | Status | Notes |
|---|---|---|
| `uploadVideo()` — multipart POST | ✅ | |
| `analyzeVideoStream()` — SSE via `fetch` + `ReadableStream` | ✅ | Replaces legacy `analyzeVideo()` |
| SSE line parser dispatching `onProgress` / `onComplete` / `onError` | ✅ | |
| `getClipUrl()` helper | ✅ | |

### VideoUpload Component (`web/src/components/VideoUpload.tsx`)

| Feature | Status | Notes |
|---|---|---|
| File picker with format + size validation | ✅ | |
| Upload progress feedback | ✅ | |
| Transitions to trim phase on success | ✅ | |

### TrimEditor Component (`web/src/components/TrimEditor.tsx`)

| Feature | Status | Notes |
|---|---|---|
| Range sliders for trim start/end | ✅ | |
| Suggested trim pre-populated from upload response | ✅ | |
| `low_confidence` warning display | ✅ | |
| **Throw Type selector** (3 options) | ✅ | |
| **Camera Perspective selector** (5 options) | ✅ | |
| Auto-detected badge when `throw_type_confidence ≥ 0.70` | ✅ | Wired to `uploadData.detected_throw_type`; badge in label |
| Low-confidence hint when `throw_type_confidence < 0.70` | ✅ | Hint `<p>` rendered between label and select |
| Analyze button disabled until both context fields have a value | ✅ | |
| Calls `analyzeVideoStream` on confirm | ✅ | |
| Renders `AnalysisProgress` inline during streaming | ✅ | |
| Shot context fields stack vertically on small screens | ✅ | |

### AnalysisProgress Component (`web/src/components/AnalysisProgress.tsx`)

| Feature | Status | Notes |
|---|---|---|
| Vertical list of 5 pipeline stages | ✅ | |
| Per-stage state: ✓ complete / ⟳ in-progress / ○ pending | ✅ | |
| Status message below stage list | ✅ | |
| `role="status"`, `aria-live="polite"`, `aria-busy` accessibility attrs | ✅ | |

### CritiqueResults Component (`web/src/components/CritiqueResults.tsx`)

| Feature | Status | Notes |
|---|---|---|
| Overall score display | ✅ | |
| Summary text | ✅ | |
| `throw_type` confirmation display | ✅ | |
| Phase breakdown (name, observations, recommendations) | ✅ | |
| `key_focus` highlight | ✅ | |
| Annotated video player (`GET /clip/{id}`) | ✅ | |
| **`camera_perspective` context display** | ⚠️ **MISSING** | Field is in the API response and TypeScript type but never rendered. See [Gap 1](#gap-1--camera-perspective-display-in-results-previously-gap-2) |

### App State Machine (`web/src/App.tsx`)

| Feature | Status | Notes |
|---|---|---|
| 3-phase state: `upload → trim → results` | ✅ | |
| `handleUploadComplete` → trim transition | ✅ | |
| `handleTrimConfirmed` → results transition | ✅ | |
| `handleReset` → upload transition | ✅ | |

---

## Infrastructure

| Feature | Status | Notes |
|---|---|---|
| `api` Dockerfile | ✅ | |
| `web` Dockerfile (Nginx) | ✅ | |
| `docker-compose.yml` with `api` + `web` services | ✅ | |
| `tmpfs` mount for `/tmp/uploads` in compose | ✅ | |
| `OPENAI_API_KEY` env variable wiring | ✅ | |
| `GET /health` liveness probe | ✅ | |

---

## Open Gaps

### Gap 1 — Camera perspective display in results *(previously Gap 2)*
**File**: [web/src/components/CritiqueResults.tsx](web/src/components/CritiqueResults.tsx)  
**Spec section**: Output Format / `camera_perspective` confirmation field

`critique.camera_perspective` is returned by the API and present in the TypeScript `CritiqueResponse` type but is never rendered in the UI.

**What needs to be built:**
- Display `camera_perspective` alongside `throw_type` in the results context summary
- Use the human-readable label from the Shot Context table (e.g. `"side_facing"` → `"Side — facing camera"`)
- Small change; the data is already flowing end-to-end

**Impact**: Low — a cosmetic omission, but specified behaviour.
