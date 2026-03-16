interface AnalysisProgressProps {
  currentStage: string | null;
  completedStages: string[];
  statusMessage: string;
}

const STAGES = [
  { key: 'clipping',   label: 'Trimming clip'          },
  { key: 'extracting', label: 'Extracting frames'       },
  { key: 'analyzing',  label: 'AI form analysis'        },
  { key: 'annotating', label: 'Annotating frames'       },
  { key: 'assembling', label: 'Building annotated clip' },
] as const;

export default function AnalysisProgress({
  currentStage,
  completedStages,
  statusMessage,
}: AnalysisProgressProps): JSX.Element {
  const totalSteps = STAGES.length;
  const completedCount = completedStages.length;
  const isProcessing = currentStage !== null && completedCount < totalSteps;

  return (
    // role="status" carries implicit aria-live="polite" — do not add aria-live explicitly
    // to avoid double-announcement in some screen readers (JAWS, VoiceOver).
    <div
      className="analysis-progress"
      role="status"
      aria-busy={isProcessing}
      tabIndex={-1}
    >
      <p className="progress-step-count">
        Step {Math.min(completedCount + 1, totalSteps)} of {totalSteps}
      </p>
      <ul className="progress-stages" aria-label="Processing stages">
        {STAGES.map(stage => {
          const isComplete = completedStages.includes(stage.key);
          const isCurrent = currentStage === stage.key;

          if (isComplete) {
            return (
              <li key={stage.key} className="progress-stage progress-stage--complete">
                <span className="stage-indicator stage-indicator--complete" aria-hidden="true">✓</span>
                <span className="stage-label">{stage.label}</span>
                <span className="sr-only"> — complete</span>
              </li>
            );
          }

          if (isCurrent) {
            return (
              <li key={stage.key} className="progress-stage progress-stage--current">
                <span className="spinner spinner--small" aria-hidden="true" />
                <span className="stage-label">{stage.label}</span>
                <span className="sr-only"> — in progress</span>
              </li>
            );
          }

          return (
            <li key={stage.key} className="progress-stage progress-stage--pending">
              <span className="stage-indicator stage-indicator--pending" aria-hidden="true">○</span>
              <span className="stage-label">{stage.label}</span>
              <span className="sr-only"> — pending</span>
            </li>
          );
        })}
      </ul>
      <p className="progress-status">{statusMessage}</p>
    </div>
  );
}
