import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { getJson, postJson } from "./api";
import {
  claimType,
  mediumDate,
  outcomeLabel,
  statusLabel,
  usd,
} from "./format";
import type { ActivityLine, Claim, Handler } from "./types";

const LIMIT = 1000;

function canPay(claim: Claim): boolean {
  if (claim.decision?.outcome !== "approve" || claim.payment !== null) {
    return false;
  }
  return claim.decision.payout <= LIMIT || claim.sign_off !== null;
}

export function ClaimPage() {
  const { claimId } = useParams();
  const [claim, setClaim] = useState<Claim | null>(null);
  const [activity, setActivity] = useState<ActivityLine[]>([]);
  const [handlers, setHandlers] = useState<Handler[]>([]);
  const [handlerId, setHandlerId] = useState("");

  useEffect(() => {
    if (claimId === undefined) return;
    let ignore = false;
    void getJson<Claim>(`/api/claims/${claimId}`).then((next) => {
      if (!ignore) setClaim(next);
    });
    void getJson<ActivityLine[]>(`/api/claims/${claimId}/activity`).then(
      (next) => {
        if (!ignore) setActivity(next);
      },
    );
    void getJson<Handler[]>("/api/handlers").then((next) => {
      if (!ignore) {
        setHandlers(next);
        setHandlerId((current) => {
          if (current !== "" || next.length === 0) return current;
          return next[0].handler_id;
        });
      }
    });
    return () => {
      ignore = true;
    };
  }, [claimId]);

  useEffect(() => {
    if (claimId === undefined) return;
    const timer = window.setInterval(() => {
      void getJson<Claim>(`/api/claims/${claimId}`).then(setClaim);
      void getJson<ActivityLine[]>(`/api/claims/${claimId}/activity`).then(
        setActivity,
      );
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [claimId]);

  if (claimId === undefined || claim === null) {
    return null;
  }

  function reload() {
    if (claimId === undefined) return;
    void getJson<Claim>(`/api/claims/${claimId}`).then(setClaim);
    void getJson<ActivityLine[]>(`/api/claims/${claimId}/activity`).then(
      setActivity,
    );
  }

  return (
    <article>
      <ClaimHeader claim={claim} />
      <div className="claim-top">
        <DecisionPanel claim={claim} />
        <div>
          <AgentPanel claim={claim} activity={activity} />
          <ClaimActions
            claim={claim}
            handlers={handlers}
            handlerId={handlerId}
            onHandlerId={setHandlerId}
            onReload={reload}
          />
        </div>
      </div>
      <ClaimStory claim={claim} />
      <PolicyPanel claim={claim} />
    </article>
  );
}

function ClaimHeader({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <p className="kicker">{claimType(claim.claim_type)}</p>
      <h2>
        <span className="claim-id">{claim.claim_id}</span> {claim.customer_name}
      </h2>
      <p className="lede">{claim.summary}</p>
      <p className="pills">
        <span className={`pill ${claim.status}`}>
          {statusLabel(claim.status)}
        </span>
        {claim.decision !== null ? (
          <span className={`pill ${claim.decision.outcome}`}>
            {outcomeLabel(claim.decision.outcome)}
          </span>
        ) : null}
      </p>
      <dl className="facts">
        <div>
          <dt>Submitted</dt>
          <dd>{mediumDate(claim.submitted_on)}</dd>
        </div>
        <div>
          <dt>Incident</dt>
          <dd>{mediumDate(claim.incident_date)}</dd>
        </div>
        <div>
          <dt>Where</dt>
          <dd>{claim.incident_location}</dd>
        </div>
        <div>
          <dt>Claimed</dt>
          <dd className="money">{usd(claim.amount_claimed)}</dd>
        </div>
        <div>
          <dt>Payout</dt>
          <dd className="money">
            {claim.decision === null ? (
              <span className="muted">Not decided</span>
            ) : (
              usd(claim.decision.payout)
            )}
          </dd>
        </div>
        <div>
          <dt>Paid</dt>
          <dd className="money">
            {claim.payment === null ? (
              <span className="muted">Not paid</span>
            ) : (
              usd(claim.payment.amount)
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function DecisionPanel({ claim }: Readonly<{ claim: Claim }>) {
  const decision = claim.decision;
  return (
    <section className="panel">
      <h3>Decision</h3>
      {decision === null ? (
        <p className="muted">
          No decision yet. The agent has not recorded an outcome, a payout, or
          the policy section it relied on.
        </p>
      ) : (
        <>
          <p className="outcome-line">
            <span className={`pill ${decision.outcome}`}>
              {outcomeLabel(decision.outcome)}
            </span>
            <span className="money">{usd(decision.payout)}</span>
          </p>
          <h4>Basis</h4>
          <p className="basis">{decision.policy_section}</p>
          <p>{decision.explanation}</p>
          {claim.status === "waiting_for_sign_off" ? (
            <p>
              This payout is over $1,000. Payment waits until a handler signs
              off.
            </p>
          ) : null}
          {claim.sign_off !== null ? (
            <p>{claim.sign_off.handler_name} signed off.</p>
          ) : null}
          {claim.payment !== null ? (
            <p>
              Paid <span className="money">{usd(claim.payment.amount)}</span>
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function AgentPanel({
  claim,
  activity,
}: Readonly<{ claim: Claim; activity: ActivityLine[] }>) {
  const working = claim.status === "in_progress";
  return (
    <section className="panel">
      <h3>Agent at work</h3>
      {working ? <p className="live">Working now</p> : null}
      {activity.length === 0 ? (
        <p className="muted">The agent has not started this claim.</p>
      ) : (
        <ol className="activity">
          {activity.map((line, index) => (
            <li key={`${String(index)}-${line.message}`}>{line.message}</li>
          ))}
        </ol>
      )}
    </section>
  );
}

function ClaimActions({
  claim,
  handlers,
  handlerId,
  onHandlerId,
  onReload,
}: Readonly<{
  claim: Claim;
  handlers: Handler[];
  handlerId: string;
  onHandlerId: (value: string) => void;
  onReload: () => void;
}>) {
  const waiting =
    claim.status === "waiting" ||
    claim.status === "in_progress" ||
    claim.status === "left_for_handler";
  const needsSignOff = claim.status === "waiting_for_sign_off";

  async function work() {
    await postJson(`/api/claims/${claim.claim_id}/run`, {
      thread_id: crypto.randomUUID(),
    });
    onReload();
  }

  async function signOff() {
    await postJson(`/api/claims/${claim.claim_id}/sign-off`, {
      handler_id: handlerId,
    });
    onReload();
  }

  async function pay() {
    if (claim.decision === null) return;
    await postJson(`/api/claims/${claim.claim_id}/payment`, {
      amount: claim.decision.payout,
    });
    onReload();
  }

  if (!waiting && !needsSignOff && !canPay(claim)) {
    return null;
  }

  return (
    <section className="panel actions">
      <h3>Actions</h3>
      {waiting ? (
        <button type="button" onClick={() => void work()}>
          Work this claim
        </button>
      ) : null}
      {needsSignOff ? (
        <label>
          Handler
          <select
            value={handlerId}
            onChange={(event) => {
              onHandlerId(event.target.value);
            }}
          >
            {handlers.map((handler) => (
              <option key={handler.handler_id} value={handler.handler_id}>
                {handler.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {needsSignOff ? (
        <button
          type="button"
          className="secondary"
          onClick={() => void signOff()}
        >
          Sign off
        </button>
      ) : null}
      {canPay(claim) ? (
        <button type="button" onClick={() => void pay()}>
          Pay
        </button>
      ) : null}
    </section>
  );
}

function ClaimStory({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h3>Story</h3>
      <p className="story">{claim.story}</p>
      <h3>Items</h3>
      <ul className="items">
        {claim.items.map((item) => (
          <li key={item.description}>
            <span>{item.description}</span>
            <span className="money">{usd(item.amount)}</span>
          </li>
        ))}
      </ul>
      <h3>Documents</h3>
      {claim.documents.map((document) => (
        <p key={document.name} className="document">
          <strong>{document.name}</strong>
          {"\n"}
          {document.content}
        </p>
      ))}
    </section>
  );
}

function PolicyPanel({ claim }: Readonly<{ claim: Claim }>) {
  const limits = claim.policy.limits;
  return (
    <section className="panel">
      <h3>Policy</h3>
      <p>
        {claim.policy.plan_name}. Travelers: {claim.policy.travelers.join(", ")}
        .
      </p>
      <dl className="facts">
        <div>
          <dt>Trip delay max</dt>
          <dd className="money">{usd(limits.trip_delay_max)}</dd>
        </div>
        <div>
          <dt>Baggage max</dt>
          <dd className="money">{usd(limits.baggage_max)}</dd>
        </div>
        <div>
          <dt>Deductible</dt>
          <dd className="money">{usd(limits.deductible)}</dd>
        </div>
      </dl>
      <h3>Earlier claims</h3>
      {claim.previous_claims.length === 0 ? (
        <p className="muted">No earlier claims.</p>
      ) : (
        <ul className="items">
          {claim.previous_claims.map((previous) => (
            <li key={previous.claim_id}>
              <span>
                <span className="claim-id">{previous.claim_id}</span>{" "}
                {previous.summary} ({previous.outcome})
              </span>
              <span className="money">{usd(previous.amount_paid)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
