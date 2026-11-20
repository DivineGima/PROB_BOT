import { describe, expect, it } from "vitest";
import list from "../../../packages/contracts/bot_commands.json";
import {
  cleanArgs,
  daysBetween,
  isCalendarDate,
  isCommandText,
  MAX_ARGS_CHARS,
  parseCommand,
  parseCountArg,
  parseDateArg,
} from "../src/commands/parse";
import { COMMAND_NAMES, COMMAND_SPECS, usageOf } from "../src/commands/registry";

/** Command grammar and the shared command list (architecture 3, section 6.10; essentials 3 step 1). */

describe("command registry", () => {
  it("equals packages/contracts/bot_commands.json, in the same order", () => {
    expect(list.commands.map((c) => c.command)).toEqual([...COMMAND_NAMES]);
    expect(COMMAND_SPECS).toEqual(list.commands);
  });

  it("holds names and descriptions Telegram's setMyCommands accepts", () => {
    for (const c of list.commands) {
      expect(c.command).toMatch(/^[a-z0-9_]{1,32}$/);
      expect(c.description.length).toBeGreaterThanOrEqual(3);
      expect(c.description.length).toBeLessThanOrEqual(256);
    }
    expect(new Set(list.commands.map((c) => c.command)).size).toBe(list.commands.length);
  });

  it("writes usage lines from the list", () => {
    expect(usageOf("fixtures")).toBe("Usage: /fixtures [today|tomorrow|YYYY-MM-DD]");
    expect(usageOf("status")).toBe("Usage: /status");
    expect(usageOf("team")).toBe("Usage: /team <name>");
  });
});

describe("parseCommand", () => {
  it("reads every known command with and without arguments", () => {
    for (const name of COMMAND_NAMES) {
      expect(parseCommand(`/${name}`)).toEqual({ kind: "command", name, args: "" });
    }
    expect(parseCommand("/fixtures tomorrow")).toEqual({
      kind: "command",
      name: "fixtures",
      args: "tomorrow",
    });
  });

  it("is case-insensitive, drops a @bot suffix and maps /start to /help", () => {
    expect(parseCommand("/STATUS")).toEqual({ kind: "command", name: "status", args: "" });
    expect(parseCommand("/status@ProbBot")).toEqual({ kind: "command", name: "status", args: "" });
    expect(parseCommand("/Results@some_bot 5")).toEqual({
      kind: "command",
      name: "results",
      args: "5",
    });
    expect(parseCommand("/start")).toEqual({ kind: "command", name: "help", args: "" });
  });

  it("cleans the arguments: spaces collapsed, control and direction characters removed", () => {
    expect(parseCommand("/team    Real‮  Madrid \u0000 ")).toEqual({
      kind: "command",
      name: "team",
      args: "Real Madrid",
    });
    expect(parseCommand("/team\tArsenal\n")).toEqual({
      kind: "command",
      name: "team",
      args: "Arsenal",
    });
  });

  it("answers usage when the arguments are over the cap", () => {
    expect(parseCommand(`/team ${"a".repeat(MAX_ARGS_CHARS)}`)).toEqual({
      kind: "command",
      name: "team",
      args: "a".repeat(MAX_ARGS_CHARS),
    });
    expect(parseCommand(`/team ${"a".repeat(MAX_ARGS_CHARS + 1)}`)).toEqual({
      kind: "usage",
      name: "team",
    });
  });

  it("treats anything else as an unknown command", () => {
    for (const text of [
      "/",
      "/rerun",
      "/rollback R1",
      "/stat",
      "/status:",
      "/status1",
      "/статус",
      `/${"a".repeat(33)}`,
      "status",
      " /status",
      "/ status",
    ]) {
      expect(parseCommand(text), text).toEqual({ kind: "unknown" });
    }
  });

  it("knows which texts are commands", () => {
    expect(isCommandText("/status")).toBe(true);
    expect(isCommandText("/")).toBe(true);
    expect(isCommandText("hello /status")).toBe(false);
    expect(isCommandText("")).toBe(false);
  });

  it("never throws on hostile input", () => {
    const nasty = [
      "/team '; DROP TABLE predictions; --",
      "/team <script>alert(1)</script>",
      `/team ${"\u{1F600}".repeat(40)}`,
      "/team \uD800",
      "/fixtures ../../etc/passwd",
    ];
    for (const text of nasty) expect(() => parseCommand(text)).not.toThrow();
  });
});

describe("cleanArgs", () => {
  it("removes zero-width and bidi characters and trims", () => {
    expect(cleanArgs("​A⁦B⁩ ﻿")).toBe("A B");
  });
});

describe("parseDateArg", () => {
  const now = new Date("2026-10-17T20:00:00Z"); // 01:30 IST on the 18th: still the 17th in UTC

  it("reads the words as UTC calendar dates", () => {
    expect(parseDateArg("", now)).toBe("2026-10-17");
    expect(parseDateArg("today", now)).toBe("2026-10-17");
    expect(parseDateArg("TOMORROW", now)).toBe("2026-10-18");
    expect(parseDateArg("Yesterday", now)).toBe("2026-10-16");
  });

  it("accepts real calendar dates only", () => {
    expect(parseDateArg("2026-10-20", now)).toBe("2026-10-20");
    expect(parseDateArg("2028-02-29", now)).toBe("2028-02-29");
    for (const bad of ["2026-02-29", "2026-13-01", "2026-10-32", "17-10-2026", "2026-1-5", "x"]) {
      expect(parseDateArg(bad, now), bad).toBeNull();
    }
  });

  it("checks calendar dates", () => {
    expect(isCalendarDate("2024-02-29")).toBe(true);
    expect(isCalendarDate("2100-02-29")).toBe(false);
  });

  it("counts days between dates", () => {
    expect(daysBetween("2026-10-17", "2026-10-21")).toBe(4);
    expect(daysBetween("2026-10-17", "2026-10-16")).toBe(-1);
    expect(daysBetween("2026-12-31", "2027-01-01")).toBe(1);
  });
});

describe("parseCountArg", () => {
  it("gives the default, accepts the range, refuses the rest", () => {
    expect(parseCountArg("", 10, 1, 20)).toBe(10);
    expect(parseCountArg("1", 10, 1, 20)).toBe(1);
    expect(parseCountArg("20", 10, 1, 20)).toBe(20);
    for (const bad of ["0", "21", "-1", "1.5", "ten", "99999"]) {
      expect(parseCountArg(bad, 10, 1, 20), bad).toBeNull();
    }
  });
});
