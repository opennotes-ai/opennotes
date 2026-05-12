import { describe, it, expect } from "vitest";
import { createSignal, For } from "solid-js";
import { render } from "@solidjs/testing-library";
import { HighlightsStoreProvider, useHighlights } from "./HighlightsStoreProvider";
import { SafetyHighlightsBridge } from "./SafetyHighlightsBridge";
import type { SafetyDivergence, SafetyRecommendationWithDivergences } from "./SafetyHighlightsBridge";

function makeDiv(
  idx: number,
  overrides: Partial<SafetyDivergence> = {},
): SafetyDivergence {
  return {
    reason: `Reason ${idx}`,
    signal_source: `source-${idx}`,
    signal_detail: `detail-${idx}`,
    ...overrides,
  };
}

function makeRec(
  divergences: SafetyDivergence[],
): SafetyRecommendationWithDivergences {
  return {
    level: "safe",
    rationale: "rationale",
    divergences,
  };
}

function ProbeItems() {
  const highlights = useHighlights();
  return (
    <div data-testid="probe">
      <For each={highlights.items()}>
        {(it) => (
          <span data-testid={`item-${it.id}`} data-source={it.source}>
            {it.title}
          </span>
        )}
      </For>
    </div>
  );
}

describe("SafetyHighlightsBridge", () => {
  it("populates two divergences in the store", () => {
    const rec = makeRec([makeDiv(0), makeDiv(1)]);
    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(getByTestId("item-safety-divergence:0").textContent).toBe("Reason 0");
    expect(getByTestId("item-safety-divergence:1").textContent).toBe("Reason 1");
  });

  it("replaces items when recommendation updates to fewer divergences", () => {
    const [rec, setRec] = createSignal<SafetyRecommendationWithDivergences | null>(
      makeRec([makeDiv(0), makeDiv(1)]),
    );

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).not.toBeNull();

    setRec(makeRec([makeDiv(0)]));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).toBeNull();
  });

  it("clears safety-divergence items when recommendation becomes null", () => {
    const [rec, setRec] = createSignal<SafetyRecommendationWithDivergences | null>(
      makeRec([makeDiv(0)]),
    );

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();

    setRec(null);

    expect(queryByTestId("item-safety-divergence:0")).toBeNull();
  });

  it("preserves items from other sources across safety-divergence refreshes", () => {
    const [rec, setRec] = createSignal<SafetyRecommendationWithDivergences | null>(
      makeRec([makeDiv(0)]),
    );

    let seedStore: ReturnType<typeof useHighlights> | undefined;

    function SeedOtherSource() {
      const highlights = useHighlights();
      seedStore = highlights;
      highlights.push("other-source", [
        { id: "other-1", source: "other-source", title: "Other title" },
      ]);
      return null;
    }

    const { queryByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SeedOtherSource />
        <SafetyHighlightsBridge recommendation={rec()} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    expect(queryByTestId("item-other-1")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();

    setRec(makeRec([makeDiv(0), makeDiv(1)]));

    expect(queryByTestId("item-other-1")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:0")).not.toBeNull();
    expect(queryByTestId("item-safety-divergence:1")).not.toBeNull();
  });

  it("maps id, title, detail, and severity correctly", () => {
    const div = makeDiv(0, {
      reason: "Suspicious pattern",
      signal_source: "model-x",
      signal_detail: "high confidence match",
    });

    const { getByTestId } = render(() => (
      <HighlightsStoreProvider>
        <SafetyHighlightsBridge recommendation={makeRec([div])} />
        <ProbeItems />
      </HighlightsStoreProvider>
    ));

    const el = getByTestId("item-safety-divergence:0");
    expect(el.textContent).toBe("Suspicious pattern");
    expect(el.getAttribute("data-source")).toBe("safety-divergence");
  });
});
