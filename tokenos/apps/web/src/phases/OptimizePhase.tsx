import { useRun } from "../state/runContext";
import { PhaseIntro, PhaseSummaryFacts, SectionHead } from "../components/shared/PhaseIntro";
import { RouteBadge } from "../components/shared/Badges";
import { GENERATIVE_ROUTES } from "../components/shared/format";

export function OptimizePhase() {
  const { state } = useRun();
  const { active } = state;
  const plan = active.plan;
  if (!plan) return null;

  const operations = active.operations.length ? active.operations : plan.operations;
  const withoutGenerative = operations.filter(
    (operation) => !GENERATIVE_ROUTES.has(operation.route)
  ).length;
  const efficient = operations.filter((operation) => operation.route === "efficient_ai").length;
  const advanced = operations.filter((operation) => operation.route === "advanced_ai").length;
  const evaluated = active.routesSelected || operations.length;

  return (
    <div className="phase">
      <PhaseIntro
        heading="Choosing the best routes"
        supporting="TokenOS compares regular software, approved retrieval and reuse, efficient AI, and advanced AI, and picks the cheapest route that still satisfies the requirements."
        focusKey="optimize"
      />

      <section className="panel">
        <SectionHead
          title={
            evaluated >= operations.length
              ? "Each operation gets its least expensive safe route"
              : `Comparing eligible routes: ${evaluated} of ${operations.length}`
          }
          supporting={
            plan.model_available
              ? "Model routes are available and are used only where reasoning is required."
              : "No Foundry deployment is configured, so model routes are unavailable and TokenOS reports what it cannot do rather than guessing."
          }
        />

        <PhaseSummaryFacts
          facts={[
            {
              value: `${withoutGenerative} without AI`,
              label: "Software, retrieval, or reuse",
              state: "passed"
            },
            { value: `${efficient} efficient AI`, label: "Bounded generation tasks", state: "passed" },
            {
              value: `${advanced} advanced AI`,
              label: "Only where deeper reasoning is needed",
              state: "passed"
            },
            {
              value: `${plan.estimated_model_calls.maximum} call ceiling`,
              label: "Maximum planned model calls",
              state: "passed"
            }
          ]}
        />

        <div className="table-wrap">
          <table>
            <caption>Route plan</caption>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Selected route</th>
                <th>Plain-language reason</th>
              </tr>
            </thead>
            <tbody>
              {operations.slice(0, Math.max(evaluated, 0)).map((operation) => (
                <tr key={operation.operation_id}>
                  <td>{operation.label}</td>
                  <td>
                    <RouteBadge route={operation.route} />
                  </td>
                  <td>{operation.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
