import { useState, useEffect, useRef, type ChangeEvent } from 'react';
import type { UploadResponse, TrimRange, AnalyzeResponse } from '../types/api';
import { analyzeVideo, ApiError } from '../api/client';

interface TrimEditorProps {
  uploadData: UploadResponse;
  /** The original File object, used to generate a local preview URL. */
  file: File;
  onConfirmed: (data: AnalyzeResponse) => void;
  onReset: () => void;
}

function msToSeconds(ms: number): string {
  return (ms / 1000).toFixed(1) + 's';
}

export default function TrimEditor({
  uploadData,
  file,
  onConfirmed,
  onReset,
}: TrimEditorProps): JSX.Element {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, []);

  const [startMs, setStartMs] = useState<number>(uploadData.suggested_trim.start_ms);
  const [endMs, setEndMs] = useState<number>(uploadData.suggested_trim.end_ms);
  const [videoSrc, setVideoSrc] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setVideoSrc(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [file]);

  const handleStartChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const value = parseInt(e.target.value, 10);
    setStartMs(Math.min(value, endMs - 100));
  };

  const handleEndChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const value = parseInt(e.target.value, 10);
    setEndMs(Math.max(value, startMs + 100));
  };

  const handleAnalyze = async (): Promise<void> => {
    setError(null);
    setIsLoading(true);
    try {
      const trim: TrimRange = { start_ms: startMs, end_ms: endMs };
      const data = await analyzeVideo({ upload_id: uploadData.upload_id, trim });
      onConfirmed(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Analysis failed: ${err.message}`);
      } else {
        setError('Analysis failed. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="trim-editor">
      <h2 ref={headingRef} tabIndex={-1}>Review Throw Segment</h2>

      {uploadData.low_confidence && (
        <div className="warning-banner" role="alert">
          Auto-detection confidence was low — please review the trim manually.
        </div>
      )}

      <video
        src={videoSrc}
        controls
        className="video-preview"
        aria-label="Uploaded video preview"
      />

      <div className="trim-controls">
        <p className="trim-display">
          {msToSeconds(startMs)} &ndash; {msToSeconds(endMs)}
        </p>

        <label htmlFor="start-range" className="trim-label">
          Start: {msToSeconds(startMs)}
        </label>
        <input
          id="start-range"
          type="range"
          min={0}
          max={uploadData.duration_ms}
          step={100}
          value={startMs}
          onChange={handleStartChange}
          className="range-input"
          aria-label="Trim start point"
          disabled={isLoading}
        />

        <label htmlFor="end-range" className="trim-label">
          End: {msToSeconds(endMs)}
        </label>
        <input
          id="end-range"
          type="range"
          min={0}
          max={uploadData.duration_ms}
          step={100}
          value={endMs}
          onChange={handleEndChange}
          className="range-input"
          aria-label="Trim end point"
          disabled={isLoading}
        />
      </div>

      {error !== null && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <div className="trim-actions">
        <button
          className="btn btn-primary"
          onClick={() => { void handleAnalyze(); }}
          disabled={isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? (
            <>
              <span className="spinner spinner--small" aria-hidden="true" />
              Analyzing…
            </>
          ) : (
            'Analyze Throw'
          )}
        </button>
        <button
          className="btn btn-secondary"
          onClick={onReset}
          disabled={isLoading}
        >
          Start Over
        </button>
      </div>
    </div>
  );
}
