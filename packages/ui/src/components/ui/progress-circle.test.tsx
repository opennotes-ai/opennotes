import { afterEach, describe, expect, it } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { ProgressCircle } from "./progress-circle";

afterEach(() => {
  cleanup();
});

describe("<ProgressCircle />", () => {
  it("renders an SVG element", () => {
    const { container } = render(() => <ProgressCircle value={50} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders two circles (track + progress arc)", () => {
    const { container } = render(() => <ProgressCircle value={50} />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBeGreaterThanOrEqual(2);
  });

  it("progress arc has stroke-dasharray and stroke-dashoffset attributes", () => {
    const { container } = render(() => <ProgressCircle value={50} />);
    const circles = container.querySelectorAll("circle");
    const arcCircle = Array.from(circles).find((c) =>
      c.hasAttribute("stroke-dasharray"),
    );
    expect(arcCircle).toBeTruthy();
    expect(arcCircle?.hasAttribute("stroke-dashoffset")).toBe(true);
  });

  it("stroke attribute is set to currentColor on both circles (arc is visible)", () => {
    const { container } = render(() => <ProgressCircle value={50} />);
    const circles = container.querySelectorAll("circle");
    for (const circle of Array.from(circles)) {
      expect(circle.getAttribute("stroke")).toBe("currentColor");
    }
  });

  it("stroke-dashoffset differs between value=0 and value=100", () => {
    const { container: c0 } = render(() => <ProgressCircle value={0} />);
    const { container: c100 } = render(() => <ProgressCircle value={100} />);

    const getOffset = (container: HTMLElement) => {
      const circles = container.querySelectorAll("circle");
      const arc = Array.from(circles).find((c) =>
        c.hasAttribute("stroke-dashoffset"),
      );
      return arc?.getAttribute("stroke-dashoffset");
    };

    const offset0 = getOffset(c0);
    const offset100 = getOffset(c100);
    expect(offset0).not.toBe(offset100);
  });

  it("value=0 renders no progress arc (dashoffset equals circumference)", () => {
    const { container } = render(() => <ProgressCircle value={0} />);
    const circles = container.querySelectorAll("circle");
    const arc = Array.from(circles).find((c) =>
      c.hasAttribute("stroke-dashoffset"),
    );
    const dashoffset = parseFloat(arc?.getAttribute("stroke-dashoffset") ?? "0");
    const dasharray = arc?.getAttribute("stroke-dasharray")?.split(" ")[0];
    const circumference = parseFloat(dasharray ?? "0");
    expect(dashoffset).toBeCloseTo(circumference, 1);
  });

  it("value=100 fills the arc completely (dashoffset near 0)", () => {
    const { container } = render(() => <ProgressCircle value={100} />);
    const circles = container.querySelectorAll("circle");
    const arc = Array.from(circles).find((c) =>
      c.hasAttribute("stroke-dashoffset"),
    );
    const dashoffset = parseFloat(arc?.getAttribute("stroke-dashoffset") ?? "1");
    expect(dashoffset).toBeCloseTo(0, 1);
  });

  it("clamps value above 100 to 100", () => {
    const { container: c100 } = render(() => <ProgressCircle value={100} />);
    const { container: c200 } = render(() => <ProgressCircle value={200} />);

    const getOffset = (container: HTMLElement) => {
      const circles = container.querySelectorAll("circle");
      const arc = Array.from(circles).find((c) =>
        c.hasAttribute("stroke-dashoffset"),
      );
      return arc?.getAttribute("stroke-dashoffset");
    };

    expect(getOffset(c100)).toBe(getOffset(c200));
  });

  it("undefined value renders as 0 (no arc progress)", () => {
    const { container } = render(() => <ProgressCircle />);
    const circles = container.querySelectorAll("circle");
    const arc = Array.from(circles).find((c) =>
      c.hasAttribute("stroke-dashoffset"),
    );
    const dashoffset = parseFloat(arc?.getAttribute("stroke-dashoffset") ?? "0");
    const dasharray = arc?.getAttribute("stroke-dasharray")?.split(" ")[0];
    const circumference = parseFloat(dasharray ?? "0");
    expect(dashoffset).toBeCloseTo(circumference, 1);
  });

  it("xs size renders smaller SVG than xl size", () => {
    const { container: cXs } = render(() => <ProgressCircle value={50} size="xs" />);
    const { container: cXl } = render(() => <ProgressCircle value={50} size="xl" />);

    const svgXs = cXs.querySelector("svg");
    const svgXl = cXl.querySelector("svg");

    const widthXs = parseFloat(svgXs?.getAttribute("width") ?? "0");
    const widthXl = parseFloat(svgXl?.getAttribute("width") ?? "0");

    expect(widthXs).toBeLessThan(widthXl);
  });

  it("renders children inside absolute container", () => {
    render(() => <ProgressCircle value={50}><span>75%</span></ProgressCircle>);
    expect(screen.getByText("75%")).toBeTruthy();
  });

  it("SVG has -rotate-90 class so arc starts at top", () => {
    const { container } = render(() => <ProgressCircle value={50} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("class")).toContain("-rotate-90");
  });
});
