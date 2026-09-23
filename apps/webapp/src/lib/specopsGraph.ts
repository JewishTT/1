/**
 * SpecOps entity-graph helpers for the webapp (Maltego-style). Pure
 * projections over the ``/entities/graph`` payload: entity-type styling,
 * Cytoscape element building, and human labels — no I/O, no state.
 */

import type { SpecOpsGraphNode, SpecOpsGraphResponse } from "./api";

/** Entity-type presentation meta (human label + icon + canvas CSS class). */
export interface EntityTypeStyle {
  label: string;
  icon: string;
  className: string;
}

export const ENTITY_TYPE_STYLES: Record<string, EntityTypeStyle> = {
  EMAIL: { label: "Email", icon: "✉", className: "so-email" },
  USERNAME: { label: "Username", icon: "@", className: "so-username" },
  PHONE: { label: "Phone", icon: "☎", className: "so-phone" },
  DOMAIN: { label: "Domain", icon: "◉", className: "so-domain" },
  URL: { label: "URL", icon: "⌕", className: "so-url" },
  NAME: { label: "Name", icon: "◈", className: "so-name" },
  ORG: { label: "Org", icon: "▤", className: "so-org" },
  LOCATION: { label: "Location", icon: "⌖", className: "so-location" },
  IPV4: { label: "IPv4", icon: "⛁", className: "so-ipv4" },
  UNKNOWN: { label: "Unknown", icon: "?", className: "so-unknown" },
};

export const FALLBACK_TYPE_STYLE: EntityTypeStyle = ENTITY_TYPE_STYLES.UNKNOWN;

/** Deterministic per-type style for an entity_type label (uppercase-safe). */
export function typeStyle(entityType: string): EntityTypeStyle {
  return ENTITY_TYPE_STYLES[entityType.trim().toUpperCase()] ?? FALLBACK_TYPE_STYLE;
}

/** Canvas accents keyed by style class — safe hex defaults for Cytoscape. */
export const ENTITY_TYPE_ACCENTS: Record<string, string> = {
  "so-email": "#b5ff69",
  "so-username": "#8ce3a0",
  "so-phone": "#8ed7db",
  "so-domain": "#82adff",
  "so-url": "#a78bfa",
  "so-name": "#f0a832",
  "so-org": "#ff8d70",
  "so-location": "#ffd166",
  "so-ipv4": "#ff6670",
  "so-unknown": "#9aac9d",
};

/** Selection target handed to the entity toolbar. */
export interface EntityToolbarTarget {
  id: string;
  label: string;
  entity_type: string;
  entity_value: string;
}

/** Human value for a node: prefers the backend label, then a property, then the id. */
export function formatEntityValue(node: SpecOpsGraphNode): string {
  const label = node.label?.trim();
  if (label && label !== node.id) return label;
  for (const key of ["account", "username", "email", "domain", "name", "value", "identity"]) {
    const value = node.properties[key];
    if (value) return value;
  }
  return node.id;
}

/** Shape a raw graph node into a toolbar selection target. */
export function toEntityTarget(node: SpecOpsGraphNode): EntityToolbarTarget {
  const value = formatEntityValue(node);
  return {
    id: node.id,
    label: node.label || value,
    entity_type: node.entity_type,
    entity_value: value,
  };
}

export interface CytoscapeElement {
  data: Record<string, unknown>;
  classes?: string;
}

/** Map a graph response to Cytoscape elements (nodes styled by class, edges labelled by kind). */
export function graphToCytoscape(graph: SpecOpsGraphResponse): CytoscapeElement[] {
  return [
    ...graph.nodes.map((node) => ({
      data: {
        id: node.id,
        label: formatEntityValue(node),
        entity_type: node.entity_type,
        entity_value: formatEntityValue(node),
        properties: node.properties,
      },
      classes: typeStyle(node.entity_type).className,
    })),
    ...graph.edges.map((edge) => ({
      data: { id: edge.id, source: edge.source, target: edge.target, label: edge.kind },
    })),
  ];
}