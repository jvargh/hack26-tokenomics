import { useRun } from "../state/runContext";
import { PhaseIntro, PhaseSummaryFacts, SectionHead } from "../components/shared/PhaseIntro";
import { formatUsd } from "../components/shared/format";
import { useState } from "react";

type PlanDetail = "operations" | "order" | "side_effects" | "inputs";

export function PlanPhase() {
  const { state } = useRun();
  const { active } = state;
  const [detail, setDetail] = useState<PlanDetail>("operations");
  const plan = active.plan;
  if (!plan) return null;

  const summary = plan.plan_summary;
  const sideEffects = plan.operations.filter((operation) => operation.side_effect).length;
  const inputEntries = Object.entries(plan.input_summary);

  return (
    <div className="phase">
      <PhaseIntro heading="Planning the work" supporting={summary.description} focusKey="plan" />

      <section className="panel">
        <SectionHead
          title={summary.title}
          supporting="TokenOS validated the supplied input and broke the outcome into inspectable operations before anything was executed."
        />

        <PhaseSummaryFacts
          selectedId={detail}
          onSelect={(id) => setDetail(id as PlanDetail)}
          detailId="plan-detail"
          facts={[
            {
              id: "operations",
              value: `${plan.operation_count} operations`,
              label: "Required for the outcome",
              state: "passed"
            },
            {
              id: "order",
              value: "Ordered safely",
              label: "Dependencies established",
              state: "passed"
            },
            {
              id: "side_effects",
              value: sideEffects === 0 ? "Side effects checked" : `${sideEffects} side effects`,
              label: "External actions identified",
              state: sideEffects === 0 ? "passed" : "warning"
            },
            {
              id: "inputs",
              value: "Inputs validated",
              label: "Read from the supplied files",
              state: "passed"
            }
          ]}
        />

        <div className="detail-pane" id="plan-detail" role="tabpanel">
          {detail === "operations" ? (
            <div className="table-wrap">
              <table>
                <caption>
                  {`Estimated model calls: ${plan.estimated_model_calls.minimum} to ${plan.estimated_model_calls.maximum}`}
                </caption>
                <thead>
                  <tr>
                    <th className="numeric">Order</th>
                    <th>Operation</th>
                    <th>Type</th>
                    <th>Planned route</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.operations.map((operation) => (
                    <tr key={operation.operation_id}>
                      <td className="numeric">{operation.order}</td>
                      <td>{operation.label}</td>
                      <td>{operation.kind}</td>
                      <td>{operation.route}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {detail === "order" ? (
            <>
              <p className="detail-lead">
                Dependencies established. An operation starts only after everything it depends on has
                completed.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th className="numeric">Order</th>
                      <th>Operation</th>
                      <th>Depends on</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.operations.map((operation) => (
                      <tr key={operation.operation_id}>
                        <td className="numeric">{operation.order}</td>
                        <td>{operation.label}</td>
                        <td>
                          {operation.depends_on.length
                            ? operation.depends_on
                                .map(
                                  (order) =>
                                    `${order}. ${
                                      plan.operations.find((item) => item.order === order)?.label ??
                                      "Unknown"
                                    }`
                                )
                                .join(" · ")
                            : "None"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {detail === "side_effects" ? (
            <>
              <p className="detail-lead">
                {sideEffects === 0
                  ? `All ${plan.operation_count} operations are read-only, so nothing in this plan can change an external system.`
                  : `${sideEffects} operation(s) can change an external system and require the configured approval.`}
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Operation</th>
                      <th>Effect</th>
                      <th>Approval required</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.operations.map((operation) => (
                      <tr key={operation.operation_id}>
                        <td>{operation.label}</td>
                        <td>
                          {operation.side_effect ? "Can change an external system" : "Read-only"}
                        </td>
                        <td>
                          {operation.side_effect || plan.requires_approval
                            ? "Yes, before execution"
                            : "No"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {detail === "inputs" ? (
            <>
              <p className="detail-lead">
                These values were read from the files you supplied, not from the outcome text.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Measured from the input</th>
                      <th>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inputEntries.map(([key, value]) => (
                      <tr key={key}>
                        <td>{key.replace(/_/g, " ")}</td>
                        <td>{Array.isArray(value) ? value.join(", ") : String(value)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td>Maximum authorized model cost</td>
                      <td>{formatUsd(plan.estimated_maximum_cost_usd)} estimated</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}
