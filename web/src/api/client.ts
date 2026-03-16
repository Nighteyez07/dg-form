import type { UploadResponse, AnalyzeResponse, TrimRequest } from '../types/api';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const json = await response.json() as Record<string, unknown>;
      if (typeof json['detail'] === 'string') {
        message = json['detail'];
      } else if (typeof json['message'] === 'string') {
        message = json['message'];
      }
    } catch {
      // keep default message
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const body = new FormData();
  body.append('video', file);

  const response = await fetch('/api/upload', {
    method: 'POST',
    body,
  });

  return handleResponse<UploadResponse>(response);
}

export async function analyzeVideo(req: TrimRequest): Promise<AnalyzeResponse> {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

  return handleResponse<AnalyzeResponse>(response);
}

export function getClipUrl(clip_id: string): string {
  return `/api/clip/${clip_id}`;
}
