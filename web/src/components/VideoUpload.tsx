import { useState, useCallback, useRef, useEffect, type DragEvent, type KeyboardEvent, type ChangeEvent } from 'react';
import type { UploadResponse } from '../types/api';
import { uploadVideo, ApiError } from '../api/client';

const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024; // 200 MB
const ACCEPTED_MIME_TYPES = ['video/mp4', 'video/quicktime', 'video/3gpp', 'video/webm'];
const ACCEPTED_FORMATS_LABEL = 'MP4, MOV, 3GP, WebM';

interface VideoUploadProps {
  onUploadComplete: (data: UploadResponse, file: File) => void;
}

function validateFile(file: File): string | null {
  if (!ACCEPTED_MIME_TYPES.includes(file.type)) {
    return `Unsupported format. Please upload one of: ${ACCEPTED_FORMATS_LABEL}.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File is too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximum size is 200 MB.`;
  }
  return null;
}

export default function VideoUpload({ onUploadComplete }: VideoUploadProps): JSX.Element {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, []);

  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(
    async (file: File): Promise<void> => {
      const validationError = validateFile(file);
      if (validationError !== null) {
        setError(validationError);
        return;
      }

      setError(null);
      setIsLoading(true);
      try {
        const data = await uploadVideo(file);
        onUploadComplete(data, file);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`Upload failed: ${err.message}`);
        } else {
          setError('Upload failed. Please try again.');
        }
      } finally {
        setIsLoading(false);
      }
    },
    [onUploadComplete]
  );

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (file !== undefined) {
      void processFile(file);
    }
    // Reset input so the same file can be re-selected after an error
    e.target.value = '';
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file !== undefined) {
      void processFile(file);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const handleZoneClick = (): void => {
    if (!isLoading) {
      fileInputRef.current?.click();
    }
  };

  const dropZoneClass = [
    'drop-zone',
    isDragging ? 'drop-zone--active' : '',
    isLoading ? 'drop-zone--loading' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="upload-container">
      <h2 ref={headingRef} tabIndex={-1}>Upload Your Throw</h2>
      <div
        className={dropZoneClass}
        role="button"
        tabIndex={0}
        aria-label="Drag &amp; drop a video here, or press Enter to open the file picker"
        aria-busy={isLoading}
        onClick={handleZoneClick}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onKeyDown={handleKeyDown}
      >
        {isLoading ? (
          <div className="upload-loading">
            <div className="spinner" role="status" aria-label="Uploading" />
            <p>Uploading and detecting throw segment…</p>
          </div>
        ) : (
          <>
            <p className="drop-zone__primary">Drag &amp; drop a video here</p>
            <p className="drop-zone__secondary">or click / press Enter to browse</p>
          </>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="video/mp4,video/quicktime,video/3gpp,video/webm"
        className="file-input-hidden"
        aria-hidden="true"
        tabIndex={-1}
        onChange={handleFileInputChange}
      />
      <p className="accepted-formats">
        Accepted formats: <strong>{ACCEPTED_FORMATS_LABEL}</strong> &middot; Max 200 MB
      </p>
      {error !== null && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
