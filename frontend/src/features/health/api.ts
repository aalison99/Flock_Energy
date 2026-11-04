import type { components } from "../../generated/schema";
import { client, unwrap } from "../../lib/api-client";

export type Readiness = components["schemas"]["ReadinessResponse"];

export function getReadiness(): Promise<Readiness> {
  return unwrap(client.GET("/api/v1/health/ready"));
}
