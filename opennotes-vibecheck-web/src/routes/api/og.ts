import type { APIEvent } from "@solidjs/start/server";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
import { pollJob } from "~/lib/api-client.server";
import type { JobState } from "~/lib/api-client.server";
import { formatWeatherLabel } from "~/lib/weather-labels";
import {
  PLEX_SANS_700_B64,
  PLEX_SANS_600_B64,
  PLEX_SERIF_400_B64,
} from "../../assets/fonts/fonts-data";

const PLEX_SANS_700 = Buffer.from(PLEX_SANS_700_B64, "base64");
const PLEX_SANS_600 = Buffer.from(PLEX_SANS_600_B64, "base64");
const PLEX_SERIF_400 = Buffer.from(PLEX_SERIF_400_B64, "base64");

const FONTS: Parameters<typeof satori>[1]["fonts"] = [
  { name: "IBM Plex Sans Condensed", data: PLEX_SANS_700, weight: 700, style: "normal" },
  { name: "IBM Plex Sans Condensed", data: PLEX_SANS_600, weight: 600, style: "normal" },
  { name: "IBM Plex Serif", data: PLEX_SERIF_400, weight: 400, style: "normal" },
];

const NON_TERMINAL_STATES = new Set(["pending", "extracting", "analyzing"] as const);
const TERMINAL_CC = "public, max-age=43200, s-maxage=43200, immutable";
const NON_TERMINAL_CC = "public, max-age=300, s-maxage=300";

const MINIMAL_TRANSPARENT_PNG = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
  0x89, 0x00, 0x00, 0x00, 0x0b, 0x49, 0x44, 0x41,
  0x54, 0x78, 0x9c, 0x62, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00,
  0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
  0x42, 0x60, 0x82,
]);

function cacheControlFor(jobState: JobState | null): string {
  if (jobState && NON_TERMINAL_STATES.has(jobState.status as "pending" | "extracting" | "analyzing")) {
    return NON_TERMINAL_CC;
  }
  return TERMINAL_CC;
}

type ElementLike = {
  type: string;
  props: {
    style?: Record<string, unknown>;
    children?: ElementLike | ElementLike[] | string | null;
    [key: string]: unknown;
  };
};

function el(
  type: string,
  style: Record<string, unknown>,
  children?: ElementLike | ElementLike[] | string | null,
): ElementLike {
  return { type, props: { style, children: children ?? null } };
}

function buildAxisGroup(label: string, value: string): ElementLike {
  return el("div", { display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }, [
    el(
      "span",
      {
        fontFamily: "IBM Plex Sans Condensed",
        fontWeight: 600,
        fontSize: 18,
        color: "#8ba8a4",
        letterSpacing: "0.14em",
        textTransform: "uppercase",
      },
      label,
    ),
    el(
      "span",
      {
        fontFamily: "IBM Plex Serif",
        fontWeight: 400,
        fontSize: 30,
        color: "#d8e0df",
      },
      value,
    ),
  ]);
}

function buildRightColumn(job: JobState): ElementLike | null {
  const report = job.sidebar_payload?.weather_report;
  if (!report) return null;

  return el(
    "div",
    {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      width: 356,
      flexShrink: 0,
      backgroundColor: "#1d2625",
      borderLeft: "1px solid #3b4847",
      gap: 44,
      padding: "60px 32px",
    },
    [
      buildAxisGroup("Truth", formatWeatherLabel(report.truth.label)),
      buildAxisGroup("Relevance", formatWeatherLabel(report.relevance.label)),
      buildAxisGroup("Sentiment", formatWeatherLabel(report.sentiment.label)),
    ],
  );
}

function buildGenericCard(): ElementLike {
  return el(
    "div",
    {
      display: "flex",
      flexDirection: "row",
      width: 1200,
      height: 630,
      backgroundColor: "#171f1e",
    },
    [
      el(
        "div",
        {
          display: "flex",
          flexDirection: "column",
          flex: 1,
          padding: "60px 64px",
          gap: 24,
          justifyContent: "center",
        },
        [
          el(
            "span",
            {
              fontFamily: "IBM Plex Sans Condensed",
              fontWeight: 700,
              fontSize: 20,
              color: "#22b09a",
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            },
            "vibecheck",
          ),
          el(
            "span",
            {
              fontFamily: "IBM Plex Sans Condensed",
              fontWeight: 700,
              fontSize: 42,
              color: "#e8f0ef",
              lineHeight: 1.2,
              maxWidth: 680,
            },
            "Analyze URLs and PDFs for tone, claims, safety, and opinions.",
          ),
        ],
      ),
    ],
  );
}

function buildJobCard(job: JobState): ElementLike {
  const title = job.page_title ?? "Vibecheck Analysis";
  let domain = "";
  if (job.url) {
    try {
      domain = new URL(job.url).hostname.replace(/^www\./, "");
    } catch {
      domain = "";
    }
  }

  const rightColumn = buildRightColumn(job);
  const leftMaxWidth = rightColumn ? "66%" : "90%";

  const leftColumn = el(
    "div",
    {
      display: "flex",
      flexDirection: "column",
      flex: 1,
      padding: "60px 64px",
      gap: 24,
      justifyContent: "center",
    },
    [
      el(
        "span",
        {
          fontFamily: "IBM Plex Sans Condensed",
          fontWeight: 700,
          fontSize: 20,
          color: "#22b09a",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        },
        "vibecheck",
      ),
      el(
        "span",
        {
          fontFamily: "IBM Plex Sans Condensed",
          fontWeight: 700,
          fontSize: 54,
          color: "#e8f0ef",
          lineHeight: 1.2,
          maxWidth: leftMaxWidth,
        },
        title,
      ),
      domain
        ? el(
            "span",
            {
              fontFamily: "IBM Plex Sans Condensed",
              fontWeight: 600,
              fontSize: 22,
              color: "#6b8a87",
            },
            domain,
          )
        : null,
    ].filter(Boolean) as ElementLike[],
  );

  return el(
    "div",
    {
      display: "flex",
      flexDirection: "row",
      width: 1200,
      height: 630,
      backgroundColor: "#171f1e",
    },
    rightColumn ? [leftColumn, rightColumn] : [leftColumn],
  );
}

async function renderCard(job: JobState | null): Promise<Uint8Array> {
  const tree = job ? buildJobCard(job) : buildGenericCard();
  const svg = await satori(tree as Parameters<typeof satori>[0], {
    width: 1200,
    height: 630,
    fonts: FONTS,
  });
  return new Resvg(svg).render().asPng();
}

async function safeRender(job: JobState | null): Promise<Uint8Array> {
  try {
    return await renderCard(job);
  } catch (err) {
    console.error("og:render-card-failed", err);
    try {
      return await renderCard(null);
    } catch (err2) {
      console.error("og:generic-fallback-also-failed", err2);
      return MINIMAL_TRANSPARENT_PNG;
    }
  }
}

export async function GET(event: APIEvent): Promise<Response> {
  const url = new URL(event.request.url);
  const jobId = url.searchParams.get("job");

  let job: JobState | null = null;
  let cacheControl: string;

  if (jobId) {
    try {
      job = await pollJob(jobId, { signal: AbortSignal.timeout(10_000) });
    } catch (error: unknown) {
      console.error(`[og] Failed to load job ${jobId}:`, error);
    }
  }

  cacheControl = cacheControlFor(job);

  const pngBytes = await safeRender(job);
  const png: BodyInit = pngBytes.buffer as ArrayBuffer;

  return new Response(png, {
    status: 200,
    headers: {
      "content-type": "image/png",
      "cache-control": cacheControl,
    },
  });
}
