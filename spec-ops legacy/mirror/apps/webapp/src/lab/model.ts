import type {
  LabCampaignWire,
  LabFigureStatusWire,
  LabReportFigureWire,
  LabSessionStateWire,
} from "../lib/api";

/**
 * Pure derivations for the lab canvas. No fetching: a row the overview does not
 * serve is `null` with a named source, never a zero that reads as a measurement.
 */

export type LabTone = "accent" | "gold" | "danger" | "neutral" | "analytical" | "strong";

export function campaignTone(state: LabCampaignWire["state"]): LabTone {
  switch (state) {
    case "complete":
      return "accent";
    case "partial":
    case "refused":
      return "danger";
    case "sending":
    case "ready":
      return "gold";
    default:
      return "neutral";
  }
}

export function sessionTone(state: LabSessionStateWire): LabTone {
  switch (state) {
    case "running":
      return "accent";
    case "stopped":
      return "gold";
    case "denied":
      return "danger";
    default:
      return "neutral";
  }
}

export function figureTone(status: LabFigureStatusWire): LabTone {
  switch (status) {
    case "measured":
      return "accent";
    case "derived":
      return "analytical";
    default:
      return "gold";
  }
}

export function figureValue(figure: LabReportFigureWire | undefined): string {
  if (!figure || figure.value === null) return "unavailable";
  return figure.value.toLocaleString();
}

export function reportFigureRows(
  figures: Record<string, LabReportFigureWire>,
): Array<{ name: string; figure: LabReportFigureWire }> {
  return Object.entries(figures).map(([name, figure]) => ({ name, figure }));
}

export function shortId(id: string, length = 14): string {
  return id.length <= length ? id : `${id.slice(0, length)}...`;
}
