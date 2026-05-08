import { afterEach, describe, expect, it } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@solidjs/testing-library";
import { WeatherHelpButton } from "./WeatherHelpButton";

afterEach(() => {
  cleanup();
});

describe("WeatherHelpButton", () => {
  it("renders a button with aria-label matching /explain.*weather/i", () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    expect(button).toBeDefined();
    expect(button.getAttribute("aria-label")).toMatch(/explain.*weather/i);
  });

  it("clicking the button reveals a popover containing Truth, Relevance, Sentiment headings", async () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    await screen.findByText(/Truth/);
    await screen.findByText(/Relevance/);
    await screen.findByText(/Sentiment/);
  });

  it("popover content includes the Truth axis explanation text", async () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    await screen.findByText(/Epistemic stance/i);
  });

  it("popover content includes the Relevance axis explanation text", async () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    await screen.findByText(/tethered to the source/i);
  });

  it("popover content includes the Sentiment axis explanation text", async () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    await screen.findByText(/emotional register/i);
  });

  it("pressing Escape closes the popover", async () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    await screen.findByText(/Epistemic stance/i);

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });

    await waitFor(() => {
      expect(screen.queryByText(/Epistemic stance/i)).toBeNull();
    });
  });

  it("button has absolute bottom-right positioning classes", () => {
    render(() => <WeatherHelpButton />);
    const button = screen.getByRole("button");
    expect(button.className).toContain("absolute");
    expect(button.className).toContain("right-2");
    expect(button.className).toContain("bottom-2");
  });

  it("accepts an optional class prop that is merged onto the trigger", () => {
    render(() => <WeatherHelpButton class="test-custom-class" />);
    const button = screen.getByRole("button");
    expect(button.className).toContain("test-custom-class");
  });
});
