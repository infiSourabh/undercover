import type { Claim, Handler, QueueClaim } from "./types";

export const handlers: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    email: "dana.whitfield@undercover.example",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-02",
    name: "Marcus Oyelaran",
    role: "Claims Handler",
    email: "marcus.oyelaran@undercover.example",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-03",
    name: "Priya Raman",
    role: "Claims Handler",
    email: "priya.raman@undercover.example",
    can_approve_over_limit: true,
  },
];

export const queueClaim: QueueClaim = {
  claim_id: "CLM-1001",
  customer_name: "Maya Patel",
  summary: "Flight home canceled by the airline, rebooked the next morning",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  amount_claimed: 420,
  status: "waiting",
  outcome: null,
  payout: null,
};

const policy: Claim["policy"] = {
  policy_id: "POL-2001",
  plan: "premium",
  plan_name: "UnderCover Premium",
  add_ons: [],
  purchased_on: "2026-04-22",
  sold_through: "Meridian Air checkout",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
  status: "active",
  limits: {
    trip_cancellation_max: 5000,
    trip_delay_waiting_hours: 6,
    trip_delay_max: 800,
    baggage_delay_waiting_hours: 12,
    baggage_delay_max: 300,
    baggage_max: 1500,
    per_item_limit: 300,
    passport_max: 250,
    emergency_medical_max: 100000,
    deductible: 50,
    deductible_applies_to: ["baggage", "emergency_medical"],
  },
};

export const claim1001: Claim = {
  claim_id: "CLM-1001",
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled by the airline, rebooked the next morning",
  story:
    "My flight home from Rome on June 18 was canceled by Meridian Air about two hours before departure because of a crew problem.",
  items: [
    {
      description: "Airport hotel, one night",
      category: "accommodation",
      amount: 245,
    },
  ],
  amount_claimed: 420,
  documents: [
    {
      name: "Hotel receipt",
      type: "receipt",
      content: "Hotel Aurelia Fiumicino. Total paid: $245.00.",
    },
  ],
  status: "in_progress",
  customer_name: "Maya Patel",
  previous_claims: [
    {
      claim_id: "CLM-0412",
      filed_on: "2024-08-19",
      incident_date: "2024-08-09",
      claim_type: "baggage_delay",
      summary: "Checked bag arrived 30 hours late in Lisbon",
      outcome: "approved",
      amount_paid: 140,
    },
  ],
  policy,
  decision: {
    outcome: "approve",
    payout: 420,
    explanation: "The delay is covered. The payout is the claimed expenses.",
    policy_section: "3. Trip Delay",
  },
  sign_off: null,
  payment: null,
};

export const claim1002: Claim = {
  ...claim1001,
  claim_id: "CLM-1002",
  customer_name: "Tom Becker",
  story: "My suitcase never arrived in Prague.",
  amount_claimed: 1150,
  status: "waiting_for_sign_off",
  decision: {
    outcome: "approve",
    payout: 1150,
    explanation: "Approved over the handler limit.",
    policy_section: "5. Baggage and Personal Effects",
  },
  sign_off: null,
  payment: null,
};

export const queueInstructions =
  "You are the UnderCover Agent working the claims queue. This run may take on at most {cap} claims.";

export const claimInstructions =
  "You are the UnderCover Agent. You decide one travel insurance claim. Read a section before you rely on it.";
