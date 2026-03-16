import type { UploadResponse, AnalyzeRequest, ProgressEvent, CompleteEvent } from '../types/api';

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

export async function analyzeVideoStream(
  req: AnalyzeRequest,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (event: CompleteEvent) => void,
  onError: (message: string) => void,
): Promise<void> {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

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
    onError(message);
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      if (!block.trim()) continue;
      let eventType = 'message';
      let dataLine = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        if (line.startsWith('data: ')) dataLine = line.slice(6).trim();
      }
      if (!dataLine) continue;
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataLine) as Record<string, unknown>;
      } catch {
        onError('Received unexpected data from server.');
        void reader.cancel();
        return;
      }

      if (eventType === 'progress') {
        onProgress(data as unknown as ProgressEvent);
      } else if (eventType === 'complete') {
        onComplete(data as unknown as CompleteEvent);
        void reader.cancel();
        return;
      } else if (eventType === 'error') {
        const errorMsg = typeof data['message'] === 'string' ? data['message'] : 'Unknown error';
        onError(errorMsg);
        void reader.cancel();
        return;
      }
    }
  }
}

export function getClipUrl(clip_id: string): string {
  return `/api/clip/${clip_id}`;
}
