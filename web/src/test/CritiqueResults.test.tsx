import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CritiqueResults from '../components/CritiqueResults';
import { mockUploadResponse, mockAnalyzeResponse } from './mocks/fixtures';

describe('CritiqueResults', () => {
  function renderComponent(onReset = vi.fn()): void {
    render(
      <CritiqueResults
        uploadData={mockUploadResponse}
        analyzeData={mockAnalyzeResponse}
        onReset={onReset}
      />
    );
  }

  it('renders summary and overall score', () => {
    renderComponent();

    expect(screen.getByText('Good form overall.')).toBeInTheDocument();
    expect(screen.getByText('7/10')).toBeInTheDocument();
  });

  it('renders throw type', () => {
    renderComponent();

    expect(screen.getByText('backhand')).toBeInTheDocument();
  });

  it('renders all phase names collapsed', () => {
    renderComponent();

    // Phase name is visible as a button in the accordion
    expect(screen.getByText('Grip & Setup')).toBeInTheDocument();
    // Phase body (observations/recommendations) is hidden until expanded
    expect(screen.queryByText('Firm grip detected')).toBeNull();
    expect(screen.queryByText('Try relaxing the grip slightly')).toBeNull();
  });

  it('expands phase details on click', async () => {
    const user = userEvent.setup();
    renderComponent();

    const phaseButton = screen.getByRole('button', { name: /Grip & Setup/i });
    expect(phaseButton).toHaveAttribute('aria-expanded', 'false');

    await user.click(phaseButton);

    expect(phaseButton).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText('Firm grip detected')).toBeInTheDocument();
    expect(screen.getByText('Try relaxing the grip slightly')).toBeInTheDocument();
  });

  it('calls onReset when "Analyze Another Throw" button is clicked', async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    renderComponent(onReset);

    await user.click(screen.getByRole('button', { name: /Analyze Another Throw/i }));

    expect(onReset).toHaveBeenCalledOnce();
  });
});
