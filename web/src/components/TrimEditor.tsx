import { useState, useEffect, useRef, type ChangeEvent } from 'react';
import type {
  UploadResponse,
  AnalyzeResponse,
  ThrowType,
  CameraPerspective,
  AnalyzeRequest,
} from '../types/api';
import { analyzeVideoStream } from '../api/client';
import AnalysisProgress from './AnalysisProgress';

interface TrimEditorProps {
  uploadData: UploadResponse;
  /** The original File object, used to generate a local preview URL. */
  file: File;
  onConfirmed: (data: AnalyzeResponse) => void;
  onReset: () => void;
}

function msToSeconds(ms: number): string {
  return (ms / 1000).toFixed(1) + ' seconds';
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
  // Pre-populate from auto-detection when confidence is sufficient.
  // Initialized directly so the value is present on first render without a
  // deferred effect (uploadData is immutable for the lifetime of this mount).
  const autoDetected =
    uploadData.detected_throw_type !== 'unknown' &&
    uploadData.throw_type_confidence >= 0.70;
  const [throwType, setThrowType] = useState<ThrowType | ''>(
    autoDetected ? uploadData.detected_throw_type : ''
  );
  const [cameraPerspective, setCameraPerspective] = useState<CameraPerspective | ''>('');
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [completedStages, setCompletedStages] = useState<string[]>([]);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const currentStageRef = useRef<string | null>(null);

  // Move focus to the progress feed when analysis starts so keyboard / AT users
  // aren't stranded on a newly-disabled button. (WCAG 2.4.3 Focus Order)
  const progressRef = useRef<HTMLDivElement>(null);
  const prevIsLoading = useRef<boolean>(false);
  useEffect(() => {
    if (isLoading && !prevIsLoading.current) {
      // Small timeout ensures the progress section has mounted.
      setTimeout(() => progressRef.current?.focus(), 0);
    }
    prevIsLoading.current = isLoading;
  }, [isLoading]);

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
    if (throwType === '' || cameraPerspective === '') return;
    setError(null);
    setIsLoading(true);
    setCurrentStage(null);
    setCompletedStages([]);
    setStatusMessage('');
    currentStageRef.current = null;

    const req: AnalyzeRequest = {
      upload_id: uploadData.upload_id,
      trim: { start_ms: startMs, end_ms: endMs },
      throw_type: throwType,
      camera_perspective: cameraPerspective,
    };

    await analyzeVideoStream(
      req,
      (event) => {
        if (currentStageRef.current !== null && currentStageRef.current !== event.stage) {
          const prevStage = currentStageRef.current;
          setCompletedStages(prev => [...prev, prevStage]);
        }
        currentStageRef.current = event.stage;
        setCurrentStage(event.stage);
        setStatusMessage(event.message);
      },
      (event) => {
        onConfirmed({ clip_id: event.clip_id, critique: event.critique });
      },
      (message) => {
        setError(`Analysis failed: ${message}`);
        setIsLoading(false);
      },
    );
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
          aria-valuetext={msToSeconds(startMs)}
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
          aria-valuetext={msToSeconds(endMs)}
          disabled={isLoading}
        />
      </div>

      <fieldset className="shot-context">
        <legend>Shot Context</legend>

        <div className="shot-context-field">
          <label htmlFor="throw-type">
            Throw Type
            <span aria-hidden="true"> *</span>
            <span className="sr-only"> (required)</span>
            {autoDetected && throwType === uploadData.detected_throw_type && (
              <span
                id="throw-type-auto-desc"
                className="auto-detected-badge"
              >
                Auto-detected
              </span>
            )}
          </label>
          {uploadData.detected_throw_type === 'unknown' &&
            uploadData.throw_type_confidence > 0 &&
            uploadData.throw_type_confidence < 0.70 && (
              <p className="hint-text" id="throw-type-confidence-hint">
                Auto-detection was low confidence — please confirm your throw type.
              </p>
            )}
          <select
            id="throw-type"
            value={throwType}
            onChange={e => setThrowType(e.target.value as ThrowType)}
            disabled={isLoading}
            required
            aria-describedby={
              autoDetected && throwType === uploadData.detected_throw_type
                ? 'throw-type-auto-desc'
                : uploadData.detected_throw_type === 'unknown' &&
                  uploadData.throw_type_confidence > 0 &&
                  uploadData.throw_type_confidence < 0.70
                    ? 'throw-type-confidence-hint'
                    : undefined
            }
          >
            <option value="" disabled>Select throw type…</option>
            <option value="backhand">Backhand</option>
            <option value="forehand">Forehand / Side throw</option>
            <option value="unknown">I’m not sure</option>
          </select>
        </div>

        <div className="shot-context-field">
          <label htmlFor="camera-perspective">
            Camera Perspective
            <span aria-hidden="true"> *</span>
            <span className="sr-only"> (required)</span>
          </label>
          <select
            id="camera-perspective"
            value={cameraPerspective}
            onChange={e => setCameraPerspective(e.target.value as CameraPerspective)}
            disabled={isLoading}
            required
          >
            <option value="" disabled>Select camera perspective…</option>
            <option value="front">Front-facing</option>
            <option value="back">Back-facing</option>
            <option value="side_facing">Side — facing camera</option>
            <option value="side_away">Side — facing away</option>
            <option value="unknown">Unknown / mixed</option>
          </select>
        </div>
      </fieldset>

      {error !== null && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      {isLoading && (
        <div ref={progressRef} tabIndex={-1} aria-label="Analysis progress">
          <AnalysisProgress
            currentStage={currentStage}
            completedStages={completedStages}
            statusMessage={statusMessage}
          />
        </div>
      )}

      <div className="trim-actions">
        {(throwType === '' || cameraPerspective === '') && !isLoading && (
          <p id="analyze-hint" className="hint-text">
            {throwType === '' && cameraPerspective === ''
              ? 'Select a throw type and camera perspective above to continue.'
              : throwType === ''
                ? 'Select a throw type above to continue.'
                : 'Select a camera perspective above to continue.'}
          </p>
        )}
        <button
          className="btn btn-primary"
          onClick={() => { void handleAnalyze(); }}
          disabled={isLoading || throwType === '' || cameraPerspective === ''}
          aria-describedby={throwType === '' || cameraPerspective === '' ? 'analyze-hint' : undefined}
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
