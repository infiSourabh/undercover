import { useEffect, useState } from "react";
import { getJson } from "./api";

interface Instructions {
  queue: string;
  claim: string;
}

export function InstructionsPage() {
  const [text, setText] = useState<Instructions | null>(null);

  useEffect(() => {
    void getJson<Instructions>("/api/instructions").then((body) => {
      setText(body);
    });
  }, []);

  return (
    <section className="panel">
      <h2>Instructions</h2>
      <h3>Running the queue</h3>
      <p className="instructions">{text?.queue}</p>
      <h3>Working a claim</h3>
      <p className="instructions">{text?.claim}</p>
    </section>
  );
}
