/**
 * Team-name normaliser for `/team` (architecture 3, section 6.10). It must give exactly the output of
 * the Python reference, `apps/fit/src/footy/aliases/normalise.py`, because `team_aliases.alias_norm`
 * is stored in that form. The shared vectors in `packages/contracts/golden/normalise.json` are checked
 * by Vitest and by pytest, so a change to either side fails CI.
 *
 * Steps, in the Python order: lower-case; transliterate a few letters NFKD does not decompose; NFKD;
 * drop combining marks; every run of characters outside a-z and 0-9 becomes one space; drop the
 * club-form tokens `fc` and `afc` unless nothing else is left.
 */

const TRANSLITERATE: Readonly<Record<string, string>> = {
  ß: "ss",
  ø: "o",
  æ: "ae",
  œ: "oe",
  ł: "l",
  đ: "d",
  ð: "d",
  þ: "th",
};

const DROPPED_TOKENS: ReadonlySet<string> = new Set(["fc", "afc"]);

export function normaliseName(name: string): string {
  let translated = "";
  for (const ch of name.toLowerCase()) translated += TRANSLITERATE[ch] ?? ch;
  const stripped = translated.normalize("NFKD").replace(/\p{M}/gu, "");
  const tokens = stripped
    .replace(/[^a-z0-9]+/g, " ")
    .split(" ")
    .filter((t) => t.length > 0);
  const kept = tokens.filter((t) => !DROPPED_TOKENS.has(t));
  return (kept.length > 0 ? kept : tokens).join(" ");
}
