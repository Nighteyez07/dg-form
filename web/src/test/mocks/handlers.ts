import { http, HttpResponse } from 'msw';
import { mockUploadResponse, mockAnalyzeResponse } from './fixtures';

export const handlers = [
  http.post('/api/upload', () => {
    return HttpResponse.json(mockUploadResponse, { status: 200 });
  }),

  http.post('/api/analyze', () => {
    return HttpResponse.json(mockAnalyzeResponse, { status: 200 });
  }),

  http.get('/api/clip/:clip_id', () => {
    return new HttpResponse(new Uint8Array([0, 0, 0, 0]).buffer, {
      status: 200,
      headers: { 'Content-Type': 'video/mp4' },
    });
  }),
];
