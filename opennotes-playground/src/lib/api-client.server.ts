import createClient from "openapi-fetch";
import { GoogleAuth } from "google-auth-library";
import type { IdTokenClient } from "google-auth-library";
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
const IDENTITY_TOKEN_MAX_RETRIES = 3;
const TOKEN_FETCH_TIMEOUT_MS = 5_000;

export class PlaygroundApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
  ) {
    super(message);
    this.name = "PlaygroundApiError";
  }
}

let authInstance: GoogleAuth | null = null;
const idTokenClientCache = new Map<string, IdTokenClient>();

function getAuthInstance(): GoogleAuth {
  if (!authInstance) {
    authInstance = new GoogleAuth();
  }
  return authInstance;
}

export async function getAuthorizationHeader(targetAudience: string): Promise<string | null> {
  if (process.env.NODE_ENV !== "production") return null;

  return new Promise<string | null>((resolve, reject) => {
    let settled = false;
    const timeoutId = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error("Identity token fetch timed out after 5s"));
      }
    }, TOKEN_FETCH_TIMEOUT_MS);

    (async () => {
      for (let attempt = 0; attempt < IDENTITY_TOKEN_MAX_RETRIES; attempt++) {
        try {
          const auth = getAuthInstance();
          let client = idTokenClientCache.get(targetAudience);
          if (!client) {
            client = await auth.getIdTokenClient(targetAudience);
            idTokenClientCache.set(targetAudience, client);
          }
          const headers = await client.getRequestHeaders();
          return headers.get("Authorization") || null;
        } catch (error) {
          if (attempt === IDENTITY_TOKEN_MAX_RETRIES - 1) throw error;
          await new Promise((r) => setTimeout(r, 100 * 2 ** attempt));
        }
      }
      return null;
    })().then(
      (value) => { if (!settled) { settled = true; clearTimeout(timeoutId); resolve(value); } },
      (error) => { if (!settled) { settled = true; clearTimeout(timeoutId); reject(error); } },
    );
  });
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
    fetch: async (request: Request) => {
      if (isProduction) {
        try {
          const token = await getAuthorizationHeader(baseUrl!);
          if (token) {
            const headers = new Headers(request.headers);
            headers.set("Authorization", token);
            request = new Request(request, { headers });
          }
        } catch (error) {
          throw new PlaygroundApiError(
            `Failed to fetch identity token: ${error instanceof Error ? error.message : String(error)}`,
            503,
          );
        }
      }
      return fetch(new Request(request, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) }));
    },
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
  sortBy: "count" | "has_score" = "count",
  filterClassification: string[] = [],
  filterStatus: string[] = [],
) {
  const client = getClient();
  const query: Record<string, unknown> = {
    "page[number]": page,
    "page[size]": pageSize,
    sort_by: sortBy,
  };
  if (filterClassification.length > 0) {
    query["filter[classification]"] = filterClassification;
  }
  if (filterStatus.length > 0) {
    query["filter[status]"] = filterStatus;
  }
  const { data, error, response } = await client.GET(
    "/api/v2/simulations/{simulation_id}/analysis/detailed",
    {
      params: {
        path: { simulation_id: id },
        query: query as { "page[number]"?: number; "page[size]"?: number; sort_by?: "count" | "has_score"; "filter[classification]"?: string[]; "filter[status]"?: string[] },
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
