import { ErrorBoundary } from "solid-js";
import { cleanup, render, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const setOptionMock = vi.fn();
const resizeMock = vi.fn();
const disposeMock = vi.fn();
const initMock = vi.fn(() => ({
  setOption: setOptionMock,
  resize: resizeMock,
  dispose: disposeMock,
}));

vi.mock("echarts/core", () => ({
  init: (...args: unknown[]) => initMock(...(args as [])),
  use: vi.fn(),
  registerTheme: vi.fn(),
}));
vi.mock("echarts/charts", () => ({
  LineChart: {},
  BarChart: {},
  ScatterChart: {},
}));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  DatasetComponent: {},
}));
vi.mock("echarts/renderers", () => ({
  CanvasRenderer: {},
}));

class ResizeObserverStub {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}

beforeEach(() => {
  setOptionMock.mockReset();
  resizeMock.mockReset();
  disposeMock.mockReset();
  initMock.mockClear();
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("<EChart /> defensive setOption wrapping", () => {
  it("renders the fallback (and does not trigger ErrorBoundary) when setOption throws", async () => {
    setOptionMock.mockImplementation(() => {
      throw new TypeError("Cannot read properties of undefined (reading 'get')");
    });

    const errorBoundaryFired = vi.fn();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { EChart } = await import("./echart");

    const { container } = render(() => (
      <ErrorBoundary
        fallback={(err) => {
          errorBoundaryFired(err);
          return <div data-testid="boundary-hit">boundary</div>;
        }}
      >
        <EChart option={{ series: [{ type: "line", data: [1, 2, 3] }] }} />
      </ErrorBoundary>
    ));

    await waitFor(() => {
      expect(container.querySelector('[data-testid="echart-fallback"]')).not.toBeNull();
    });

    expect(errorBoundaryFired).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="boundary-hit"]')).toBeNull();
    expect(disposeMock).toHaveBeenCalledTimes(1);

    const logged = errorSpy.mock.calls.map((c) => String(c[0])).join("\n");
    expect(logged).toMatch(/\[echart\] setOption failed:/);
  });

  it("renders the chart container normally when setOption does not throw", async () => {
    setOptionMock.mockImplementation(() => {});

    const { EChart } = await import("./echart");

    const { container } = render(() => (
      <EChart option={{ series: [{ type: "bar", data: [1] }] }} />
    ));

    await waitFor(() => {
      expect(setOptionMock).toHaveBeenCalled();
    });

    expect(container.querySelector('[data-testid="echart-fallback"]')).toBeNull();
    expect(disposeMock).not.toHaveBeenCalled();
  });

  it("renders the fallback when init itself throws (and does not bubble)", async () => {
    initMock.mockImplementationOnce(() => {
      throw new TypeError("init blew up");
    });

    const errorBoundaryFired = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { EChart } = await import("./echart");

    const { container } = render(() => (
      <ErrorBoundary
        fallback={(err) => {
          errorBoundaryFired(err);
          return <div data-testid="boundary-hit">boundary</div>;
        }}
      >
        <EChart option={{ series: [{ type: "scatter", data: [] }] }} />
      </ErrorBoundary>
    ));

    await waitFor(() => {
      expect(container.querySelector('[data-testid="echart-fallback"]')).not.toBeNull();
    });

    expect(errorBoundaryFired).not.toHaveBeenCalled();
  });
});
