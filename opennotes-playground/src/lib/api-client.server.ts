import createClient from "openapi-fetch";
import type { paths, components } from "./generated-types";

export type SimulationListResponse =
  components["schemas"]["SimulationListResponse"];
export type SimulationSingleResponse =
  components["schemas"]["SimulationSingleResponse"];
export type AnalysisResponse = components["schemas"]["AnalysisResponse"];
export type DetailedAnalysisResponse =
  components["schemas"]["DetailedAnalysisResponse"];
export type ResultsListResponse = components["schemas"]["ResultsListResponse"];

const FETCH_TIMEOUT_MS = 10_000;

export class PlaygroundApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message);
    this.name = "PlaygroundApiError";
  }
}

function getClient() {
  const isProduction = process.env.NODE_ENV === "production";

  const baseUrl = process.env.OPENNOTES_SERVER_URL || (isProduction ? undefined : "http://localhost:8000");
  const apiKey = process.env.OPENNOTES_API_KEY?.trim() || (isProduction ? undefined : "");

  if (isProduction && !baseUrl) {
    throw new Error("OPENNOTES_SERVER_URL environment variable is required in production");
  }
  if (isProduction && !apiKey) {
    throw new Error("OPENNOTES_API_KEY environment variable is required in production");
  }

  return createClient<paths>({
    baseUrl: baseUrl!,
    headers: { "X-API-Key": apiKey! },
    fetch: (request: Request) =>
      fetch(new Request(request, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })),
  });
}

export async function listSimulations(page = 1, pageSize = 20) {
  const client = getClient();
  const { data, error, response } = await client.GET("/api/v2/simulations", {
    params: {
      query: { "page[number]": page, "page[size]": pageSize },
    },
  });
  if (error) throw new PlaygroundApiError(`Failed to list simulations: ${JSON.stringify(error)}`, response.status);
  return data;
}

export async function getSimulation(id: string) {
  const client = getClient();
  const { data, error, response } = await client.GET(
    "/api/v2/simulations/{simulation_id}",
    { params: { path: { simulation_id: id } } },
  );
  if (error) throw new PlaygroundApiError(`Failed to get simulation ${id}: ${JSON.stringify(error)}`, response.status);
  return data;
}

export async function getSimulationAnalysis(id: string) {
  const client = getClient();
  const { data, error, response } = await client.GET(
    "/api/v2/simulations/{simulation_id}/analysis",
    { params: { path: { simulation_id: id } } },
  );
  if (error) throw new PlaygroundApiError(`Failed to get simulation analysis ${id}: ${JSON.stringify(error)}`, response.status);
  return data;
}

export async function getSimulationDetailedAnalysis(
  id: string,
  page = 1,
  pageSize = 20,
) {
  const client = getClient();
  const { data, error, response } = await client.GET(
    "/api/v2/simulations/{simulation_id}/analysis/detailed",
    {
      params: {
        path: { simulation_id: id },
        query: { "page[number]": page, "page[size]": pageSize },
      },
    },
  );
  if (error) throw new PlaygroundApiError(`Failed to get detailed analysis ${id}: ${JSON.stringify(error)}`, response.status);
  return data;
}

export async function getSimulationResults(
  id: string,
  page = 1,
  pageSize = 20,
) {
  const client = getClient();
  const { data, error, response } = await client.GET(
    "/api/v2/simulations/{simulation_id}/results",
    {
      params: {
        path: { simulation_id: id },
        query: { "page[number]": page, "page[size]": pageSize },
      },
    },
  );
  if (error) throw new PlaygroundApiError(`Failed to get simulation results ${id}: ${JSON.stringify(error)}`, response.status);
  return data;
}
