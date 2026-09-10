import type { PowerMeterDiagnostic } from "./api";
import type { LutMode, MeasurementRequest, MeasureType, OperatingPoint } from "./measurement";

export type SessionState =
  | "idle"
  | "validating"
  | "ready"
  | "awaiting_confirmation"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "resumable";

export interface PreflightResponse {
  valid: boolean;
  warnings: string[];
  estimated_variations?: number | null;
  estimated_duration_seconds?: number | null;
  supported_modes?: LutMode[] | null;
  power_meter_diagnostic?: PowerMeterDiagnostic | null;
  battery_level_entity_id?: string | null;
  battery_level_attribute?: string | null;
  light_load_probe?: {
    checked_variations: number;
    minimum_aggregate_power_w: number;
    points: {
      label: string;
      mode: LutMode;
      power_w: number;
    }[];
  } | null;
}

export interface SessionProgress {
  completed: number;
  total: number;
  skipped?: number;
  percent?: number;
  estimated_remaining_seconds?: number | null;
}

export interface SessionSnapshot {
  session_id?: string;
  state: SessionState;
  can_analyse?: boolean;
  created_at?: string;
  updated_at?: string;
  phase?: string | null;
  confirmation_message?: string | null;
  confirmation_action?: string | null;
  mode?: string | null;
  progress?: SessionProgress;
  warnings?: string[];
  error?: { code?: string; message: string } | string | null;
  summary?: Record<string, string> | null;
  request?: MeasurementRequest;
  operating_point?: OperatingPoint | null;
  calibration_sample?: {
    power: number;
    resistance: number;
    voltage: number;
  } | null;
  entity_states?: Record<string, string>;
}

export interface SessionSummary {
  session_id: string;
  state: SessionState;
  created_at: string;
  updated_at: string;
  measure_type: MeasureType;
  model_id: string;
  product_name: string;
  measure_device: string;
  completed: number;
  total: number;
  percent: number;
  can_resume: boolean;
  file_count: number;
  size: number;
  active: boolean;
}

export interface SessionFile {
  name: string;
  size: number;
  media_type: string;
}

export interface PlotPoint {
  x: number;
  y: number;
  color: string | null;
}

export interface PlotSeries {
  label: string | null;
  color: string | null;
  points: PlotPoint[];
}

export interface PlotSpec {
  id: string;
  title: string;
  kind: "scatter" | "line";
  x_label: string;
  y_label: string;
  source: string;
  series: PlotSeries[];
}

export interface PlotCollection {
  partial: boolean;
  plots: PlotSpec[];
  warnings: string[];
}

/** A collection with nothing plotted yet, used as the initial and the reset value. */
export function emptyPlots(warnings: string[] = []): PlotCollection {
  return { partial: false, plots: [], warnings };
}

/**
 * Payload of a regular session event. Progress, phase and state all reach the app through the
 * snapshot that rides along with the event, so only live/log fields are read from the payload.
 */
export interface SessionEventData {
  message?: string;
  power?: number;
  resistance?: number;
  voltage?: number;
  states?: Record<string, string>;
}

/** Event types the stream subscribes to. The server sends each one as its own SSE event name. */
export const REGULAR_SESSION_EVENT_TYPES = [
  "phase",
  "progress",
  "state",
  "warning",
  "log",
  "checkpoint",
  "heartbeat",
  "sample",
  "calibration_sample",
  "entity_states",
] as const;

export const SESSION_EVENT_TYPES = [...REGULAR_SESSION_EVENT_TYPES, "operating_point"] as const;

interface RegularSessionEvent {
  sequence: number;
  type: (typeof REGULAR_SESSION_EVENT_TYPES)[number];
  data: SessionEventData;
  snapshot?: SessionSnapshot;
}

interface OperatingPointSessionEvent {
  sequence: number;
  type: "operating_point";
  data: OperatingPoint;
  snapshot?: SessionSnapshot;
}

export type SessionEvent = RegularSessionEvent | OperatingPointSessionEvent;
