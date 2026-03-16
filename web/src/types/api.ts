export interface TrimRange {
  start_ms: number;
  end_ms: number;
}

export interface SuggestedTrim {
  start_ms: number;
  end_ms: number;
}

export interface UploadResponse {
  upload_id: string;
  duration_ms: number;
  suggested_trim: SuggestedTrim;
  low_confidence: boolean;
}

export interface TrimRequest {
  upload_id: string;
  trim: TrimRange;
}

export interface ThrowPhase {
  name: string;
  timestamp_ms: number;
  observations: string[];
  recommendations: string[];
}

export interface CritiqueResponse {
  overall_score: string;
  summary: string;
  throw_type: 'backhand' | 'forehand' | 'unknown';
  phases: ThrowPhase[];
  key_focus: string;
}

export interface AnalyzeResponse {
  clip_id: string;
  critique: CritiqueResponse;
}
