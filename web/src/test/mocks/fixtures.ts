import type { UploadResponse, AnalyzeResponse } from '../../types/api';

export const mockUploadResponse: UploadResponse = {
  upload_id: '550e8400-e29b-41d4-a716-446655440000',
  duration_ms: 8000,
  suggested_trim: { start_ms: 1000, end_ms: 4000 },
  low_confidence: false,
};

export const mockAnalyzeResponse: AnalyzeResponse = {
  clip_id: '550e8400-e29b-41d4-a716-446655440001',
  critique: {
    overall_score: '7/10',
    summary: 'Good form overall.',
    throw_type: 'backhand',
    phases: [
      {
        name: 'Grip & Setup',
        timestamp_ms: 1000,
        observations: ['Firm grip detected'],
        recommendations: ['Try relaxing the grip slightly'],
      },
    ],
    key_focus: 'Follow through extension',
  },
};
