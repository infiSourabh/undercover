import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getJson } from "./api";
import { claimType, mediumDate, statusLabel, todoLabel, usd } from "./format";
import type { ClaimStatus, QueueClaim, QueueRun } from "./types";

const STATUSES: ClaimStatus[] = [
  "waiting",
  "in_progress",
  "waiting_for_sign_off",
  "decided",
  "left_for_handler",
];

export function QueuePage() {
  const [claims, setClaims] = useState<QueueClaim[]>([]);
  const [run, setRun] = useState<QueueRun | null>(null);

  useEffect(() => {
    let ignore = false;
    const load = () => {
      void getJson<QueueClaim[]>("/api/claims").then((next) => {
        if (!ignore) setClaims(next);
      });
      void getJson<QueueRun>("/api/runs/current")
        .then((next) => {
          if (!ignore) setRun(next);
        })
        .catch(() => {
          if (!ignore) setRun(null);
        });
    };
    load();
    const timer = window.setInterval(load, 1000);
    return () => {
      ignore = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Queue</h2>
        <ul className="stats">
          {STATUSES.map((status) => (
            <li key={status} className={`pill ${status}`}>
              {claims.filter((claim) => claim.status === status).length}{" "}
              {statusLabel(status)}
            </li>
          ))}
        </ul>
      </div>
      <RunList run={run} />
      <ul className="queue-list">
        {claims.map((claim) => (
          <li key={claim.claim_id} className="queue-row">
            <Link className="claim-id" to={`/claims/${claim.claim_id}`}>
              {claim.claim_id}
            </Link>
            <div className="queue-main">
              <p className="queue-who">
                {claim.customer_name}
                <span className="muted">
                  {mediumDate(claim.submitted_on)} ·{" "}
                  {claimType(claim.claim_type)}
                </span>
              </p>
              <p className="queue-summary">{claim.summary}</p>
            </div>
            <dl className="queue-money">
              <div>
                <dt>Claimed</dt>
                <dd className="money">{usd(claim.amount_claimed)}</dd>
              </div>
              <div>
                <dt>Payout</dt>
                <dd className="money">
                  {claim.payout === null ? (
                    <span className="muted">Not decided</span>
                  ) : (
                    usd(claim.payout)
                  )}
                </dd>
              </div>
            </dl>
            <span className={`pill ${claim.status}`}>
              {statusLabel(claim.status)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RunList({ run }: Readonly<{ run: QueueRun | null }>) {
  if (run === null) {
    return <p>No run yet</p>;
  }
  return (
    <div>
      <h3>This run</h3>
      <p className="muted">Up to {run.max_claims} claims</p>
      <ul className="run-list">
        {run.items.map((item) => (
          <li key={item.claim_id}>
            <span className="claim-id">{item.claim_id}</span>
            <span className={`pill ${item.status}`}>
              {todoLabel(item.status)}
            </span>
          </li>
        ))}
      </ul>
      {run.summary !== null ? <p>{run.summary}</p> : null}
    </div>
  );
}
