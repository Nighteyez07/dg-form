import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import TrimEditor from '../components/TrimEditor';
import { server } from './mocks/server';
import { mockUploadResponse, mockAnalyzeResponse } from './mocks/fixtures';

// jsdom does not implement these – provide minimal stubs
Object.defineProperty(URL, 'createObjectURL', { writable: true, value: vi.fn(() => 'blob:mock') });
Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeFile(): File {
  return new File([new Uint8Array(1024)], 'throw.mp4', { type: 'video/mp4' });
}

describe('TrimEditor', () => {
  it('renders the heading and time display', () => {
    render(
      <TrimEditor
        uploadData={mockUploadResponse}
        file={makeFile()}
        onConfirmed={vi.fn()}
        onReset={vi.fn()}
      />
    );

    expect(screen.getByRole('heading', { name: /Review Throw Segment/i })).toBeInTheDocument();
    // start_ms 1000 → "1.0s", end_ms 4000 → "4.0s"
    expect(screen.getByText(/Start: 1\.0s/i)).toBeInTheDocument();
    expect(screen.getByText(/End: 4\.0s/i)).toBeInTheDocument();
  });

  it('shows warning banner when low_confidence is true', () => {
    render(
      <TrimEditor
        uploadData={{ ...mockUploadResponse, low_confidence: true }}
        file={makeFile()}
        onConfirmed={vi.fn()}
        onReset={vi.fn()}
      />
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Auto-detection confidence was low/i)).toBeInTheDocument();
  });

  it('does not show warning banner when low_confidence is false', () => {
    render(
      <TrimEditor
        uploadData={mockUploadResponse}
        file={makeFile()}
        onConfirmed={vi.fn()}
        onReset={vi.fn()}
      />
    );

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('calls onReset when cancel button clicked', async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();

    render(
      <TrimEditor
        uploadData={mockUploadResponse}
        file={makeFile()}
        onConfirmed={vi.fn()}
        onReset={onReset}
      />
    );

    await user.click(screen.getByRole('button', { name: /start over/i }));

    expect(onReset).toHaveBeenCalledOnce();
  });

  it('calls onConfirmed with analyze response on successful submission', async () => {
    const user = userEvent.setup();
    const onConfirmed = vi.fn();

    render(
      <TrimEditor
        uploadData={mockUploadResponse}
        file={makeFile()}
        onConfirmed={onConfirmed}
        onReset={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: /analyze throw/i }));

    await waitFor(() => {
      expect(onConfirmed).toHaveBeenCalledOnce();
    });
    expect(onConfirmed).toHaveBeenCalledWith(mockAnalyzeResponse);
  });

  it('shows error message on analyze API failure', async () => {
    server.use(
      http.post('/api/analyze', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      )
    );

    const user = userEvent.setup();

    render(
      <TrimEditor
        uploadData={mockUploadResponse}
        file={makeFile()}
        onConfirmed={vi.fn()}
        onReset={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: /analyze throw/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/Analysis failed/i);
  });
});
