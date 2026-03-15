# dg-form

AI-powered disc golf throw analysis. Upload a video of your throw, let the app auto-detect and clip the relevant segment, then receive GPT-4o powered form critique with an annotated video and structured text feedback.

## Features

- **Smart auto-clip** — MediaPipe pose detection identifies the throw window automatically; you fine-tune before submitting
- **AI form critique** — GPT-4o Vision analyzes key frames and breaks down your throw by phase (grip, reach-back, pull-through, release, follow-through)
- **Annotated video** — critique overlaid directly onto your clip so you can see exactly what's being referenced
- **Smartphone-first** — accepts MP4, MOV, 3GP, and WebM (covers default formats from iOS and Android cameras)
- **Privacy-respecting** — all video files are deleted immediately after processing completes; nothing is stored

## Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12 + FastAPI |
| Video processing | OpenCV + MediaPipe + FFmpeg |
| AI critique | OpenAI GPT-4o Vision |
| Frontend | React + Vite (TypeScript) |
| Deployment | Docker Compose |

## Getting Started

> Full setup instructions coming once the initial scaffold is complete.

### Prerequisites

- Docker & Docker Compose
- An OpenAI API key

### Quick start

```bash
git clone https://github.com/Nighteyez07/dg-form.git
cd dg-form
cp .env.example .env          # add your OPENAI_API_KEY
docker compose up --build
```

Then open [http://localhost:5173](http://localhost:5173).

## Project Structure

```
dg-form/
├── api/          # FastAPI backend (video processing, OpenAI integration)
├── web/          # React + Vite frontend
├── SPEC.md       # Full project specification
└── docker-compose.yml
```

## License

MIT — see [LICENSE](LICENSE).
