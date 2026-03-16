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
- An OpenAI API key with access to GPT-4o (see below)

### Obtaining an OpenAI API key

1. Go to [platform.openai.com](https://platform.openai.com) and sign in or create an account.
2. In the top-right menu, click your profile → **Your profile**, then navigate to the [API keys](https://platform.openai.com/api-keys) page in the left sidebar.
3. Click **Create new secret key**, give it a name (e.g. `dg-form`), and click **Create secret key**.
4. Copy the key immediately — it is only shown once.
5. Ensure your account has access to the **GPT-4o** model. New accounts may need to add a [payment method](https://platform.openai.com/account/billing) and have a positive credit balance before the API becomes active.

> **Cost note:** Each analyze request sends ~10 JPEG frames to GPT-4o Vision. At current pricing this is roughly $0.01–$0.05 per critique.

### Quick start

```bash
git clone https://github.com/Nighteyez07/dg-form.git
cd dg-form
cp .env.example .env          # paste your OPENAI_API_KEY into .env
docker compose up --build
```

Then open [http://localhost:5173](http://localhost:5173).

## Development Setup

### Install the pre-commit hook
After cloning, run once to enforce tests before every commit:
```sh
bash scripts/install-hooks.sh
```

### Run tests manually
```sh
# Backend (from api/)
python -m pytest

# Frontend (from web/)
npm run test

# With coverage report
npm run test:coverage
```

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
