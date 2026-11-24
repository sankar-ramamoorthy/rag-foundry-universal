// Compile-time contract check: every committed fixture (the same files the
// Python contract tests validate against the OpenAPI schema) must be
// assignable to the generated TypeScript type for its route. JSON imports are
// widened (string, not a literal), so string literals in the target type are
// widened too: enum values are checked by the Python schema validation, while
// this catches missing, renamed and mistyped fields.
import type { Schemas } from "./client";
import askNoRange from "../../fixtures/product/ask_no_range_citations.json";
import askOk from "../../fixtures/product/ask_ok.json";
import askStale from "../../fixtures/product/ask_stale.json";
import filesOk from "../../fixtures/product/files_ok.json";
import capabilitiesOk from "../../fixtures/product/capabilities_ok.json";
import investigationCitation from "../../fixtures/product/investigation_citation_ok.json";
import investigationNone from "../../fixtures/product/investigation_finished_none.json";
import investigationPartial from "../../fixtures/product/investigation_finished_partial.json";
import investigationRunning from "../../fixtures/product/investigation_running.json";
import investigationStaleGen from "../../fixtures/product/investigation_stale_generation.json";
import locateOk from "../../fixtures/product/locate_ok.json";
import orientOk from "../../fixtures/product/orient_ok.json";
import readinessNoCommit from "../../fixtures/product/readiness_no_commit.json";
import readinessReady from "../../fixtures/product/readiness_ready.json";
import reposList from "../../fixtures/product/repos_list.json";
import sourcePartial from "../../fixtures/product/source_partial.json";
import sourceStale from "../../fixtures/product/source_stale.json";
import sourceWhole from "../../fixtures/product/source_whole_file.json";

type Widen<T> = T extends string
  ? string
  : T extends (infer U)[]
    ? Widen<U>[]
    : T extends object
      ? { [K in keyof T]: Widen<T[K]> }
      : T;

/** Compiles only when the fixture body has every required field with a
 * compatible type. */
function conforms<T>(body: Widen<T>): T {
  return body as unknown as T;
}

export const checked = {
  repos: conforms<Schemas["ProductRepoList"]>(reposList.body),
  readiness: [
    conforms<Schemas["Readiness"]>(readinessReady.body),
    conforms<Schemas["Readiness"]>(readinessNoCommit.body),
  ],
  orient: conforms<Schemas["ProductOrient"]>(orientOk.body),
  files: conforms<Schemas["ProductFiles"]>(filesOk.body),
  locate: conforms<Schemas["ProductLocate"]>(locateOk.body),
  source: [
    conforms<Schemas["ProductSource"]>(sourcePartial.body),
    conforms<Schemas["ProductSource"]>(sourceWhole.body),
  ],
  ask: [
    conforms<Schemas["ProductAsk"]>(askOk.body),
    conforms<Schemas["ProductAsk"]>(askNoRange.body),
  ],
  capabilities: conforms<Schemas["Capabilities"]>(capabilitiesOk.body),
  citation: conforms<Schemas["InvestigationCitationText"]>(investigationCitation.body),
  investigations: [
    conforms<Schemas["ProductInvestigation"]>(investigationRunning.body),
    conforms<Schemas["ProductInvestigation"]>(investigationPartial.body),
    conforms<Schemas["ProductInvestigation"]>(investigationNone.body),
  ],
  errors: [
    conforms<Schemas["ProductErrorResponse"]>(investigationStaleGen.body),
    conforms<Schemas["ProductErrorResponse"]>(sourceStale.body),
    conforms<Schemas["ProductErrorResponse"]>(askStale.body),
  ],
};
