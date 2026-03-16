export type ThrowType = 'backhand' | 'forehand' | 'unknown';

export type CameraPerspective = 'front' | 'back' | 'side_facing' | 'side_away' | 'unknown';

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

export interface AnalyzeRequest {
  upload_id: string;
  trim: TrimRange;
  throw_type: ThrowType;
  camera_perspective: CameraPerspective;
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
  throw_type: ThrowType;
  phases: ThrowPhase[];
  key_focus: string;
  camera_perspective: CameraPerspective;
}

export interface AnalyzeResponse {
  clip_id: string;
  critique: CritiqueResponse;
}

export interface ProgressEvent {
  stage: string;
  message: string;
  step: number;
  total_steps: number;
}

export interface CompleteEvent {
  clip_id: string;
  critique: CritiqueResponse;
}

export interface ErrorEvent {
  message: string;
}
