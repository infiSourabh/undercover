export type ClaimStatus =
  | "waiting"
  | "in_progress"
  | "waiting_for_sign_off"
  | "decided"
  | "left_for_handler";

export type TodoStatus = "todo" | "in_progress" | "done" | "left_for_handler";

export interface TodoItem {
  claim_id: string;
  status: TodoStatus;
}

export interface QueueRun {
  run_id: string;
  max_claims: number;
  summary: string | null;
  items: TodoItem[];
}

export type Outcome = "approve" | "decline" | "refer";

export interface QueueClaim {
  claim_id: string;
  customer_name: string;
  summary: string;
  claim_type: string;
  submitted_on: string;
  amount_claimed: number;
  status: ClaimStatus;
  outcome: Outcome | null;
  payout: number | null;
}

export interface Decision {
  outcome: Outcome;
  payout: number;
  explanation: string;
  policy_section: string;
}

export interface SignOff {
  handler_id: string;
  handler_name: string;
}

export interface Payment {
  amount: number;
}

export interface ClaimItem {
  description: string;
  category: string;
  amount: number;
}

export interface ClaimDocument {
  name: string;
  type: string;
  content: string;
}

export interface PreviousClaim {
  claim_id: string;
  filed_on: string;
  incident_date: string;
  claim_type: string;
  summary: string;
  outcome: string;
  amount_paid: number;
}

export interface PolicyLimits {
  trip_cancellation_max: number;
  trip_delay_waiting_hours: number;
  trip_delay_max: number;
  baggage_delay_waiting_hours: number;
  baggage_delay_max: number;
  baggage_max: number;
  per_item_limit: number;
  passport_max: number;
  emergency_medical_max: number;
  deductible: number;
  deductible_applies_to: string[];
}

export interface Policy {
  policy_id: string;
  plan: string;
  plan_name: string;
  add_ons: { add_on: string; name: string; effect: string }[];
  purchased_on: string;
  sold_through: string;
  trip: {
    destination: string;
    departs_on: string;
    returns_on: string;
    trip_cost: number;
  };
  travelers: string[];
  status: string;
  limits: PolicyLimits;
}

export interface Claim {
  claim_id: string;
  policy_id: string;
  customer_id: string;
  claim_type: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  summary: string;
  story: string;
  items: ClaimItem[];
  amount_claimed: number;
  documents: ClaimDocument[];
  status: ClaimStatus;
  customer_name: string;
  previous_claims: PreviousClaim[];
  policy: Policy;
  decision: Decision | null;
  sign_off: SignOff | null;
  payment: Payment | null;
}

export interface Handler {
  handler_id: string;
  name: string;
  role: string;
  email: string;
  can_approve_over_limit: boolean;
}

export interface ActivityLine {
  message: string;
}
