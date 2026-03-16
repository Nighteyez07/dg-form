import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import App from '../App';
import { server } from './mocks/server';
import { mockUploadResponse, mockAnalyzeResponse } from './mocks/fixtures';
import type { UploadResponse, AnalyzeResponse } from '../types/api';

// Mock child components so we can exercise App's state machine in isolation.
// Each mock calls its relevant callback when the user triggers the action.
vi.mock('../components/VideoUpload', () => ({
  default: ({ onUploadComplete }: { onUploadComplete: (data: UploadResponse, file: File) => void }) => (
    <button
      data-testid="video-upload"
      onClick={() => onUploadComplete(mockUploadResponse, new File([], 'throw.mp4', { type: 'video/mp4' }))}
    >
      VideoUpload
    </button>
  ),
}));

vi.mock('../components/TrimEditor', () => ({
  default: ({
    onConfirmed,
    onReset,
  }: {
    onConfirmed: (data: AnalyzeResponse) => void;
    onReset: () => void;
  }) => (
    <div data-testid="trim-editor">
      <button onClick={() => onConfirmed(mockAnalyzeResponse)}>Confirm</button>
      <button onClick={onReset}>Reset</button>
    </div>
  ),
}));

vi.mock('../components/CritiqueResults', () => ({
  default: ({ onReset }: { onReset: () => void }) => (
    <div data-testid="critique-results">
      <button onClick={onReset}>Reset</button>
    </div>
  ),
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('App state machine', () => {
  it('renders VideoUpload on initial load', () => {
    render(<App />);
    expect(screen.getByTestId('video-upload')).toBeInTheDocument();
    expect(screen.queryByTestId('trim-editor')).not.toBeInTheDocument();
    expect(screen.queryByTestId('critique-results')).not.toBeInTheDocument();
  });

  it('transitions to trim phase after upload', async () => {
    render(<App />);
    await act(async () => {
      screen.getByTestId('video-upload').click();
    });
    expect(screen.getByTestId('trim-editor')).toBeInTheDocument();
    expect(screen.queryByTestId('video-upload')).not.toBeInTheDocument();
  });

  it('transitions to results phase after analyze', async () => {
    render(<App />);

    // Upload phase → trim phase
    await act(async () => {
      screen.getByTestId('video-upload').click();
    });

    // Trim phase → results phase
    await act(async () => {
      screen.getByText('Confirm').click();
    });

    expect(screen.getByTestId('critique-results')).toBeInTheDocument();
    expect(screen.queryByTestId('trim-editor')).not.toBeInTheDocument();
  });

  it('resets to upload phase on reset', async () => {
    render(<App />);

    // Advance to results
    await act(async () => {
      screen.getByTestId('video-upload').click();
    });
    await act(async () => {
      screen.getByText('Confirm').click();
    });

    expect(screen.getByTestId('critique-results')).toBeInTheDocument();

    // Trigger reset
    await act(async () => {
      screen.getByText('Reset').click();
    });

    expect(screen.getByTestId('video-upload')).toBeInTheDocument();
    expect(screen.queryByTestId('critique-results')).not.toBeInTheDocument();
  });
});
