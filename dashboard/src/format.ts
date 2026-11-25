import type { ClaimStatus, Outcome, TodoStatus } from "./types";

const STATUS_LABELS: Record<ClaimStatus, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_sign_off: "Waiting for sign-off",
  decided: "Decided",
  left_for_handler: "Left for a handler",
};

const TODO_LABELS: Record<TodoStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
  left_for_handler: "Left for a handler",
};

const OUTCOME_LABELS: Record<Outcome, string> = {
  approve: "Approved",
  decline: "Declined",
  refer: "Referred",
};

const CLAIM_TYPES: Record<string, string> = {
  trip_delay: "Trip delay",
  trip_cancellation: "Trip cancellation",
  trip_interruption: "Trip interruption",
  baggage: "Baggage",
  baggage_delay: "Baggage delay",
  emergency_medical: "Emergency medical",
  passport: "Passport",
};

export function usd(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}

export function statusLabel(status: ClaimStatus): string {
  return STATUS_LABELS[status];
}

export function todoLabel(status: TodoStatus): string {
  return TODO_LABELS[status];
}

export function outcomeLabel(outcome: Outcome): string {
  return OUTCOME_LABELS[outcome];
}

export function claimType(value: string): string {
  return CLAIM_TYPES[value] ?? value.replaceAll("_", " ");
}

export function mediumDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(Date.UTC(Number(year), Number(month) - 1, Number(day)));
}
