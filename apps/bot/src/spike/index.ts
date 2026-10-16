import { MAX_SPIKE_BODY_BYTES } from "../config/constants";
import { primeModels, runWorkload, SpikeInputError } from "./workload";

/**
 * Stage 1 CPU spike endpoint (ADR-013). Reached only through `auth` (path + header) and only
 * while `SPIKE_ENABLED=1`. The caller posts a synthetic payload built by `scripts/cpu-spike.mjs`;
 * CPU time is read afterwards from Workers Logs (`cpuTime`), not measured here, because in-Worker
 * timers do not advance during compute (section 8.10).
 *
 * @deprecated Once the Stage 1 gate is recorded in docs/verification.md, set SPIKE_ENABLED back to
 * "0". The module is kept (never deleted outright) until Stage 5 has re-measured the real path.
 */
export async function handleSpike(request: Request): Promise<Response> {
  // Preparation call from the driver: build the synthetic model data, do no measured work.
  if (request.headers.get("x-spike-prime") === "1") {
    primeModels();
    return new Response(null, { status: 204 });
  }

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_SPIKE_BODY_BYTES) return new Response(null, { status: 413 });

  const text = await request.text();
  if (text.length > MAX_SPIKE_BODY_BYTES) return new Response(null, { status: 413 });

  try {
    const result = runWorkload(text);
    return Response.json(result);
  } catch (error) {
    if (error instanceof SpikeInputError) {
      return Response.json({ error: "E_SCHEMA_INVALID", detail: error.message }, { status: 400 });
    }
    throw error;
  }
}
