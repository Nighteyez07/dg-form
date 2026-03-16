import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import VideoUpload from '../components/VideoUpload';
import { server } from './mocks/server';
import { mockUploadResponse } from './mocks/fixtures';
import type { UploadResponse } from '../types/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeFile(options: { name?: string; type?: string; size?: number } = {}): File {
  const { name = 'throw.mp4', type = 'video/mp4', size = 1024 } = options;
  const content = new Uint8Array(size);
  const file = new File([content], name, { type });
  return file;
}

describe('VideoUpload', () => {
  it('renders upload drop zone with accepted formats label', () => {
    render(<VideoUpload onUploadComplete={vi.fn()} />);
    expect(screen.getByText(/MP4, MOV, 3GP, WebM/i)).toBeInTheDocument();
  });

  it('rejects files over 200MB before uploading', async () => {
    const user = userEvent.setup();
    const onUploadComplete = vi.fn();
    render(<VideoUpload onUploadComplete={onUploadComplete} />);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const oversizedFile = makeFile({ size: 210 * 1024 * 1024 });
    await user.upload(input!, oversizedFile);

    expect(await screen.findByText(/too large/i)).toBeInTheDocument();
    expect(onUploadComplete).not.toHaveBeenCalled();
  });

  it('rejects unsupported MIME type before uploading', async () => {
    const user = userEvent.setup();
    const onUploadComplete = vi.fn();
    render(<VideoUpload onUploadComplete={onUploadComplete} />);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const aviFile = makeFile({ name: 'throw.avi', type: 'video/avi' });
    // fireEvent bypasses user-event's accept-attribute filter so the component
    // receives the unsupported MIME type and can reject it itself.
    fireEvent.change(input!, { target: { files: [aviFile] } });

    expect(await screen.findByText(/unsupported format/i)).toBeInTheDocument();
    expect(onUploadComplete).not.toHaveBeenCalled();
  });

  it('shows loading state during upload', async () => {
    let resolveUpload!: () => void;
    server.use(
      http.post('/api/upload', () =>
        new Promise<Response>((resolve) => {
          resolveUpload = () =>
            resolve(HttpResponse.json(mockUploadResponse) as unknown as Response);
        })
      )
    );

    const user = userEvent.setup();
    render(<VideoUpload onUploadComplete={vi.fn()} />);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const file = makeFile();
    await user.upload(input!, file);

    const dropZone = screen.getByRole('button', { name: /drop a video/i });
    await waitFor(() => {
      expect(dropZone).toHaveAttribute('aria-busy', 'true');
    });

    resolveUpload();
  });

  it('calls onUploadComplete on success', async () => {
    const user = userEvent.setup();
    const onUploadComplete = vi.fn<(data: UploadResponse, file: File) => void>();
    render(<VideoUpload onUploadComplete={onUploadComplete} />);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const file = makeFile();
    await user.upload(input!, file);

    await waitFor(() => {
      expect(onUploadComplete).toHaveBeenCalledOnce();
    });
    const [responseArg] = onUploadComplete.mock.calls[0];
    expect(responseArg).toEqual(mockUploadResponse);
  });

  it('shows error on API failure', async () => {
    server.use(
      http.post('/api/upload', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      )
    );

    const user = userEvent.setup();
    render(<VideoUpload onUploadComplete={vi.fn()} />);

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const file = makeFile();
    await user.upload(input!, file);

    expect(await screen.findByText(/upload failed/i)).toBeInTheDocument();
  });

  it('drop zone responds to Enter key by triggering file input click', async () => {
    const user = userEvent.setup();
    render(<VideoUpload onUploadComplete={vi.fn()} />);

    const dropZone = screen.getByRole('button', { name: /drop a video/i });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    const clickSpy = vi.spyOn(input!, 'click');

    dropZone.focus();
    await user.keyboard('{Enter}');

    expect(clickSpy).toHaveBeenCalledOnce();
  });
});
