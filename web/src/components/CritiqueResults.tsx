import { useState, useRef, useEffect } from 'react';
import type { UploadResponse, AnalyzeResponse, ThrowPhase } from '../types/api';
import { getClipUrl } from '../api/client';

interface CritiqueResultsProps {
  uploadData: UploadResponse;
  analyzeData: AnalyzeResponse;
  onReset: () => void;
}

interface PhaseItemProps {
  phase: ThrowPhase;
  index: number;
}

function PhaseItem({ phase, index }: PhaseItemProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const headingId = `phase-heading-${index}`;
  const bodyId = `phase-body-${index}`;

  return (
    <div className="phase-item">
      <button
        id={headingId}
        className="phase-header"
        aria-expanded={isExpanded}
        aria-controls={bodyId}
        onClick={() => { setIsExpanded((prev) => !prev); }}
      >
        <span className="phase-name">{phase.name}</span>
        <span className="phase-time">{(phase.timestamp_ms / 1000).toFixed(1)}s</span>
        <span className="phase-chevron" aria-hidden="true">
          {isExpanded ? '▲' : '▼'}
        </span>
      </button>
      {isExpanded && (
        <div
          id={bodyId}
          role="region"
          aria-labelledby={headingId}
          className="phase-body"
        >
          {phase.observations.length > 0 && (
            <div className="phase-section">
              <h4>Observations</h4>
              <ul>
                {phase.observations.map((obs, i) => (
                  <li key={i}>{obs}</li>
                ))}
              </ul>
            </div>
          )}
          {phase.recommendations.length > 0 && (
            <div className="phase-section">
              <h4>Recommendations</h4>
              <ul>
                {phase.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function CritiqueResults({
  uploadData,
  analyzeData,
  onReset,
}: CritiqueResultsProps): JSX.Element {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, []);

  const { critique } = analyzeData;
  const clipUrl = getClipUrl(analyzeData.clip_id);

  return (
    <div className="critique-results">
      <h2 ref={headingRef} tabIndex={-1}>Throw Analysis</h2>

      <div className="critique-overview">
        <div className="critique-meta">
          <span className="critique-throw-type">
            Throw type: <strong>{critique.throw_type}</strong>
          </span>
          <span className="critique-score">
            Score: <strong>{critique.overall_score}</strong>
          </span>
          <span className="critique-duration">
            Duration: <strong>{(uploadData.duration_ms / 1000).toFixed(1)}s</strong>
          </span>
        </div>
        <p className="critique-summary">{critique.summary}</p>
        <div className="critique-key-focus">
          <strong>Key Focus:</strong> {critique.key_focus}
        </div>
      </div>

      <section className="critique-phases" aria-label="Throw phases">
        <h3>Phase Breakdown</h3>
        {critique.phases.map((phase, i) => (
          <PhaseItem key={i} phase={phase} index={i} />
        ))}
      </section>

      <section className="critique-video" aria-label="Annotated clip">
        <h3>Annotated Clip</h3>
        <video
          src={clipUrl}
          controls
          autoPlay
          className="video-preview"
          aria-label="Annotated throw video"
        />
      </section>

      <button className="btn btn-primary" onClick={onReset}>
        Analyze Another Throw
      </button>
    </div>
  );
}
