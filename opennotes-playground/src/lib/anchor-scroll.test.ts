import { describe, expect, it } from "vitest";
import { formatIdBadgeLabel } from "./format";
import { parseFragment, findPageForItem } from "./anchor-scroll";

const UUID_A = "0195a3bc-3dc8-7f2b-9e07-c4e21c0f5a10";
const UUID_B = "019ceaaf-1234-7000-8000-aabbccddeeff";

const items = [{ id: UUID_A }, { id: UUID_B }];

describe("parseFragment", () => {
  it("returns correct AnchorTarget for valid note hash with UUID", () => {
    const result = parseFragment(`#note-${UUID_A}`, items, "note");
    expect(result).toEqual({ type: "note", id: UUID_A });
  });

  it("resolves proquint hash to UUID", () => {
    const proquint = formatIdBadgeLabel(UUID_A);
    const result = parseFragment(`#note-${proquint}`, items, "note");
    expect(result).toEqual({ type: "note", id: UUID_A });
  });

  it("returns null for non-matching prefix", () => {
    const result = parseFragment(`#agent-${UUID_A}`, items, "note");
    expect(result).toBeNull();
  });

  it("returns null for empty hash", () => {
    expect(parseFragment("", items, "note")).toBeNull();
  });

  it("returns null for hash without # prefix", () => {
    expect(parseFragment("note-abc", items, "note")).toBeNull();
  });

  it("returns null when item not found", () => {
    const result = parseFragment("#note-00000000-0000-4000-8000-000000000000", items, "note");
    expect(result).toBeNull();
  });
});

describe("findPageForItem", () => {
  const agents = [
    { agent_profile_id: "a1" },
    { agent_profile_id: "a2" },
    { agent_profile_id: "a3" },
    { agent_profile_id: "a4" },
    { agent_profile_id: "a5" },
  ];

  it("returns page 1 for first item with pageSize 2", () => {
    const page = findPageForItem(agents, "a1", 2, (a) => a.agent_profile_id);
    expect(page).toBe(1);
  });

  it("returns page 1 for second item with pageSize 2", () => {
    const page = findPageForItem(agents, "a2", 2, (a) => a.agent_profile_id);
    expect(page).toBe(1);
  });

  it("returns page 2 for third item with pageSize 2", () => {
    const page = findPageForItem(agents, "a3", 2, (a) => a.agent_profile_id);
    expect(page).toBe(2);
  });

  it("returns page 3 for fifth item with pageSize 2", () => {
    const page = findPageForItem(agents, "a5", 2, (a) => a.agent_profile_id);
    expect(page).toBe(3);
  });

  it("returns 1 if item not found", () => {
    const page = findPageForItem(agents, "missing", 2, (a) => a.agent_profile_id);
    expect(page).toBe(1);
  });

  it("returns page 1 for any item when pageSize covers all", () => {
    const page = findPageForItem(agents, "a5", 10, (a) => a.agent_profile_id);
    expect(page).toBe(1);
  });
});
