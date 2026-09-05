import { useEffect, useRef } from "react";

interface PhaseIntroProps {
  heading: string;
  supporting?: string;
  /** Focus is moved to the phase heading whenever the phase changes. */
  focusKey?: string;
}

/** Centred phase heading and one-line explanation, shown above the phase panel. */
export function PhaseIntro({ heading, supporting, focusKey }: PhaseIntroProps) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, [focusKey]);

  return (
    <div className="phase-intro">
      <h2 ref={ref} tabIndex={-1}>
        {heading}
      </h2>
      {supporting ? <p>{supporting}</p> : null}
    </div>
  );
}

export function SectionHead({ title, supporting }: { title: string; supporting?: string }) {
  return (
    <div className="section-head">
      <h3>{title}</h3>
      {supporting ? <p>{supporting}</p> : null}
    </div>
  );
}

export interface Fact {
  id?: string;
  value: string;
  label: string;
  state?: "pending" | "passed" | "warning" | "failed";
}

interface FactsProps {
  facts: Fact[];
  /** When provided the facts become a single-select group that drives a detail pane. */
  selectedId?: string;
  onSelect?: (id: string) => void;
  detailId?: string;
}

export function PhaseSummaryFacts({ facts, selectedId, onSelect, detailId }: FactsProps) {
  if (!onSelect) {
    return (
      <div className="facts">
        {facts.map((fact) => (
          <div key={fact.label} className={`fact ${fact.state ? `is-${fact.state}` : ""}`}>
            <div className="fact-value">{fact.value}</div>
            <div className="fact-label">{fact.label}</div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="facts" role="tablist" aria-label="Plan summary">
      {facts.map((fact) => {
        const id = fact.id ?? fact.label;
        const selected = id === selectedId;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            id={`fact-${id}`}
            aria-selected={selected}
            aria-controls={detailId}
            className={`fact fact-button ${fact.state ? `is-${fact.state}` : ""} ${
              selected ? "is-selected" : ""
            }`}
            onClick={() => onSelect(id)}
          >
            <span className="fact-value">{fact.value}</span>
            <span className="fact-label">{fact.label}</span>
          </button>
        );
      })}
    </div>
  );
}
