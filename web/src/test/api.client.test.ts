import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import { http, HttpResponse } from 'msw';
import { uploadVideo, analyzeVideoStream, getClipUrl, ApiError } from '../api/client';
import type { AnalyzeRequest, CompleteEvent } from '../types/api';
import { server } from './mocks/server';
import { mockUploadResponse, mockAnalyzeResponse } from './mocks/fixtures';

const mockAnalyzeRequest: AnalyzeRequest = {
  upload_id: mockUploadResponse.upload_id,
  trim: mockUploadResponse.suggested_trim,
  throw_type: 'backhand',
  camera_perspective: 'side_facing',
};

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('uploadVideo', () => {
  it('resolves with UploadResponse on success', async () => {
    const file = new File(['video-content'], 'throw.mp4', { type: 'video/mp4' });
    const result = await uploadVideo(file);
    expect(result).toEqual(mockUploadResponse);
  });

  it('throws ApiError on 415', async () => {
    server.use(
      http.post('/api/upload', () =>
        HttpResponse.json({ detail: 'Unsupported media type' }, { status: 415 })
      )
    );
    const file = new File(['video-content'], 'throw.avi', { type: 'video/avi' });
    await expect(uploadVideo(file)).rejects.toSatisfy(
      (err: unknown) => err instanceof ApiError && err.status === 415
    );
  });

  it('throws ApiError on 413', async () => {
    server.use(
      http.post('/api/upload', () =>
        HttpResponse.json({ detail: 'File too large' }, { status: 413 })
      )
    );
    const file = new File(['video-content'], 'huge.mp4', { type: 'video/mp4' });
    await expect(uploadVideo(file)).rejects.toSatisfy(
      (err: unknown) => err instanceof ApiError && err.status === 413
    );
  });
});

describe('analyzeVideoStream', () => {
  it('calls onComplete with critique on success', async () => {
    let completed: CompleteEvent | null = null;
    await analyzeVideoStream(
      mockAnalyzeRequest,
      () => {},
      (event) => { completed = event; },
      (msg) => { throw new Error(msg); },
    );
    expect(completed).not.toBeNull();
    expect(completed!.clip_id).toBe(mockAnalyzeResponse.clip_id);
    expect(completed!.critique).toEqual(mockAnalyzeResponse.critique);
  });

  it('calls onError on 404', async () => {
    server.use(
      http.post('/api/analyze', () =>
        HttpResponse.json({ detail: 'Upload not found' }, { status: 404 })
      )
    );
    let errorMsg = '';
    await analyzeVideoStream(
      { ...mockAnalyzeRequest, upload_id: 'nonexistent-id' },
      () => {},
      () => { throw new Error('should not complete'); },
      (msg) => { errorMsg = msg; },
    );
    expect(errorMsg).toMatch(/Upload not found/);
  });
});

describe('getClipUrl', () => {
  it('returns correct URL', () => {
    expect(getClipUrl('abc123')).toBe('/api/clip/abc123');
  });
});

describe('ApiError', () => {
  it('has correct status and message', () => {
    const err = new ApiError(422, 'test');
    expect(err.status).toBe(422);
    expect(err.message).toBe('test');
  });
});
