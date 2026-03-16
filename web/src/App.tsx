import { useState } from 'react';
import './App.css';
import VideoUpload from './components/VideoUpload';
import TrimEditor from './components/TrimEditor';
import CritiqueResults from './components/CritiqueResults';
import type { UploadResponse, AnalyzeResponse } from './types/api';

type Phase = 'upload' | 'trim' | 'results';

export default function App(): JSX.Element {
  const [phase, setPhase] = useState<Phase>('upload');
  const [uploadData, setUploadData] = useState<UploadResponse | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [analyzeData, setAnalyzeData] = useState<AnalyzeResponse | null>(null);

  const handleUploadComplete = (data: UploadResponse, file: File): void => {
    setUploadData(data);
    setUploadFile(file);
    setAnalyzeData(null);
    setPhase('trim');
  };

  const handleTrimConfirmed = (data: AnalyzeResponse): void => {
    setAnalyzeData(data);
    setPhase('results');
  };

  const handleReset = (): void => {
    setPhase('upload');
    setUploadData(null);
    setUploadFile(null);
    setAnalyzeData(null);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>dg-form</h1>
        <p className="app-subtitle">Disc golf throw form critique</p>
      </header>
      <main className="app-main">
        {phase === 'upload' && (
          <VideoUpload onUploadComplete={handleUploadComplete} />
        )}
        {phase === 'trim' && uploadData !== null && uploadFile !== null && (
          <TrimEditor
            uploadData={uploadData}
            file={uploadFile}
            onConfirmed={handleTrimConfirmed}
            onReset={handleReset}
          />
        )}
        {phase === 'results' && uploadData !== null && analyzeData !== null && (
          <CritiqueResults
            uploadData={uploadData}
            analyzeData={analyzeData}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  );
}
