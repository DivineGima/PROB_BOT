import list from "../../../../packages/contracts/bot_commands.json";

/**
 * The command registry (architecture 3, section 6.10, ADR-052). The names are a TypeScript list so
 * the handlers can be typed; the argument hints and descriptions come from the one shared list,
 * `packages/contracts/bot_commands.json`, which `scripts/set-webhook.mjs` also uses for Telegram's
 * menu. A test fails if the two lists differ.
 */
export const COMMAND_NAMES = [
  "status",
  "fixtures",
  "logged",
  "results",
  "pending",
  "report",
  "last",
  "team",
  "alerts",
  "help",
] as const;

export type CommandName = (typeof COMMAND_NAMES)[number];

/** Telegram sends `/start` when a chat is opened; it shows the help text. */
export const COMMAND_ALIASES: Readonly<Record<string, CommandName>> = { start: "help" };

export interface CommandSpec {
  command: string;
  args: string;
  description: string;
}

export const COMMAND_SPECS: readonly CommandSpec[] = list.commands;

const NAME_SET: ReadonlySet<string> = new Set(COMMAND_NAMES);

export function isCommandName(name: string): name is CommandName {
  return NAME_SET.has(name);
}

/** "Usage: /fixtures [today|tomorrow|YYYY-MM-DD]" for one command. */
export function usageOf(name: CommandName): string {
  const spec = COMMAND_SPECS.find((c) => c.command === name);
  return `Usage: /${name}${spec?.args ? ` ${spec.args}` : ""}`;
}
