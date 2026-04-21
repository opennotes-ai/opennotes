// FIXME(TASK-1471.16): regenerate via `pnpm run types:generate` once BE-9 (TASK-1471.14) lands openapi.json.
// Until then, this hand-rolled shape mirrors the SidebarPayload contract drafted in the implementation plan
// AND mirrors the operation/path shape that openapi-typescript emits (so openapi-fetch's type inference works).
// Do not expand this by hand — edit the Pydantic model in opennotes-vibecheck-server, run the server's
// openapi export, and regenerate via openapi-typescript. See opennotes-playground/src/lib/generated-types.ts
// for a real sample of the generated structure this will be replaced with.

export interface paths {
  "/api/analyze": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: operations["analyze_api_analyze_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}

export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    AnalyzeRequest: {
      url: string;
    };
    FlashpointScore: {
      score: number;
      label: string;
    };
    SCDNotes: {
      tone_label: string;
      dynamics_notes: string;
    };
    ToneDynamics: {
      flashpoint: components["schemas"]["FlashpointScore"] | null;
      scd: components["schemas"]["SCDNotes"] | null;
    };
    Claim: {
      claim: string;
      prevalence: number;
      representative_quote: string;
    };
    KnownMisinformation: {
      claim: string;
      fact_check_url: string;
      verdict: string;
    };
    FactsClaims: {
      claims: components["schemas"]["Claim"][];
      known_misinformation: components["schemas"]["KnownMisinformation"][];
    };
    SentimentStats: {
      positive_pct: number;
      negative_pct: number;
      neutral_pct: number;
    };
    OpinionsSentiments: {
      sentiment_stats: components["schemas"]["SentimentStats"];
      subjective_claims: string[];
    };
    HarmfulContent: {
      flagged: boolean;
      categories: string[];
    };
    SidebarSections: {
      tone_dynamics: components["schemas"]["ToneDynamics"];
      facts_claims: components["schemas"]["FactsClaims"];
      opinions_sentiments: components["schemas"]["OpinionsSentiments"];
      harmful_content: components["schemas"]["HarmfulContent"] | null;
    };
    SidebarPayload: {
      source_url: string;
      page_title: string | null;
      sections: components["schemas"]["SidebarSections"];
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}

export type $defs = Record<string, never>;

export interface operations {
  analyze_api_analyze_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["AnalyzeRequest"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["SidebarPayload"];
        };
      };
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": unknown;
        };
      };
    };
  };
}
