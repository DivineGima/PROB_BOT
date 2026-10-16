// @ts-check
// deploy.yml guard (architecture section 9.7, compensating control 2): refuse to deploy a commit that
// is not the merge of a pull request, because GitHub Free private repos cannot enforce branch protection.
import { fileURLToPath } from "node:url";

/**
 * @typedef {{ merged_at: string | null, merge_commit_sha: string | null, base?: { ref?: string } }} PullRequest
 */

/**
 * A commit may be deployed only if some pull request into `main` was merged and produced exactly this commit.
 * @param {string} sha
 * @param {unknown} pulls response of GET /repos/{repo}/commits/{sha}/pulls
 * @returns {{ ok: boolean, reason: string }}
 */
export function isMergedPrCommit(sha, pulls) {
  if (!/^[0-9a-f]{40}$/.test(sha)) return { ok: false, reason: "not a full commit sha" };
  if (!Array.isArray(pulls)) return { ok: false, reason: "unexpected API response" };
  const match = /** @type {PullRequest[]} */ (pulls).find(
    (pr) => pr?.merged_at && pr.merge_commit_sha === sha && pr.base?.ref === "main",
  );
  return match
    ? { ok: true, reason: "commit is the merge of a pull request into main" }
    : { ok: false, reason: "no merged pull request into main produced this commit (direct push?)" };
}

/**
 * @param {{ repo: string, sha: string, token: string, fetchImpl?: typeof fetch }} options
 */
export async function verifyMergedPr({ repo, sha, token, fetchImpl = fetch }) {
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return { ok: false, reason: "invalid repository name" };
  const response = await fetchImpl(`https://api.github.com/repos/${repo}/commits/${sha}/pulls`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!response.ok) return { ok: false, reason: `GitHub API answered HTTP ${response.status}` };
  return isMergedPrCommit(sha, await response.json());
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { GITHUB_REPOSITORY = "", GITHUB_SHA = "", GITHUB_TOKEN = "" } = process.env;
  const result = await verifyMergedPr({
    repo: GITHUB_REPOSITORY,
    sha: GITHUB_SHA,
    token: GITHUB_TOKEN,
  });
  console.log(`verify-merged-pr: ${result.ok ? "ok" : "REFUSED"} - ${result.reason}`);
  process.exitCode = result.ok ? 0 : 1;
}
