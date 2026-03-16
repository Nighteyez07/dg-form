import { http, HttpResponse } from 'msw';
import { mockUploadResponse, mockAnalyzeResponse } from './fixtures';

export const handlers = [
  http.post('/api/upload', () => {
    return HttpResponse.json(mockUploadResponse, { status: 200 });
  }),

  http.post('/api/analyze', () => {
    const encoder = new TextEncoder();
    const completePayload = {
      clip_id: mockAnalyzeResponse.clip_id,
      critique: mockAnalyzeResponse.critique,
    };
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: queued\ndata: {"message":"Waiting for a slot"}\n\n')
        );
        controller.enqueue(
          encoder.encode(`event: complete\ndata: ${JSON.stringify(completePayload)}\n\n`)
        );
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }),

  http.get('/api/clip/:clip_id', () => {
    return new HttpResponse(new Uint8Array([0, 0, 0, 0]).buffer, {
      status: 200,
      headers: { 'Content-Type': 'video/mp4' },
    });
  }),
];
