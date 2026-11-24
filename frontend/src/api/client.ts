// Typed product API client. The types come from openapi/product.openapi.json
// (generated into schema.d.ts by `npm run generate:api`); this file adds no
// hand-written response shapes.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type ProductError = Schemas["ProductError"];
export type ProductErrorCode = ProductError["code"];

/** Same-origin by default: browser paths are identical in development and
 * production (the dev proxy and the gateway both map /v1/product). */
export function createProductClient(baseUrl = "") {
  return createClient<paths>({ baseUrl });
}

export type ProductClient = ReturnType<typeof createProductClient>;
