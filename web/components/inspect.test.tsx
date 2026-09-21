import { NoulGauge } from "@/components/NoulGauge";
import { ProbabilityBar } from "@/components/ProbabilityBar";
import { ScoreAxis } from "@/components/ScoreAxis";
import { Waterfall } from "@/components/Waterfall";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

describe("Waterfall", () => {
  it("renders stage widths from durations", () => {
    const { getByTestId } = render(
      <Waterfall
        root={{
          name: "classify",
          duration_ms: 200,
          children: [
            { name: "gmail_fetch", duration_ms: 0, offset_ms: 0 },
            { name: "parse", duration_ms: 20, offset_ms: 0 },
            { name: "jev_call", duration_ms: 180, offset_ms: 20, retries: 2, rate_limited: true },
          ],
        }}
      />,
    );
    const root = getByTestId("waterfall");
    const jev = root.querySelector('[data-span="jev_call"]') as HTMLElement;
    expect(jev.dataset.duration).toBe("180");
    expect(jev.dataset.rateLimited).toBe("true");
    expect(root.querySelector("[data-retries]")?.getAttribute("data-retries")).toBe("2");
  });
});

describe("ProbabilityBar", () => {
  it("keeps probability and confidence distinct at 0 and 1", () => {
    const { getByTestId } = render(
      <ProbabilityBar
        probabilities={{ spam: 1, phishing: 0, promotional: 0, legitimate: 0, other: 0 }}
        winner="spam"
        confidence={0}
      />,
    );
    const el = getByTestId("probability-bar");
    expect(el.querySelector('[data-option="spam"]')?.getAttribute("data-probability")).toBe("1");
    expect(el.querySelector("[data-confidence]")?.getAttribute("data-confidence")).toBe("0");
  });
});

describe("NoulGauge", () => {
  it("marks exact threshold", () => {
    const { getByTestId } = render(<NoulGauge value={0.75} threshold={0.75} />);
    expect(getByTestId("noul-gauge").getAttribute("data-at-threshold")).toBe("true");
  });

  it("clamps 0 and 1", () => {
    const zero = render(<NoulGauge value={0} threshold={0.8} />);
    expect(zero.getByTestId("noul-gauge").getAttribute("data-value")).toBe("0");
    zero.unmount();
    const one = render(<NoulGauge value={1} threshold={0.8} />);
    expect(one.getByTestId("noul-gauge").getAttribute("data-value")).toBe("1");
  });
});

describe("ScoreAxis", () => {
  it("flags fractional positions", () => {
    const { getByTestId } = render(
      <ScoreAxis value={0.5} criteria={["None", "Mild", "Urgent"]} />,
    );
    expect(getByTestId("score-axis").getAttribute("data-fractional")).toBe("true");
  });
});
