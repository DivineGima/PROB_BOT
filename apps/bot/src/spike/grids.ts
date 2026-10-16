/**
 * Stage 1 CPU spike (ADR-013): real-shaped grid maths used only to measure Worker CPU. This is
 * NOT the production engine and NOT the numerical reference. Stage 5 builds `engine/` against
 * the Python golden vectors. Nothing here may be imported outside `src/spike`.
 */
export const GRID_SIZE = 13;
export const CELLS = GRID_SIZE * GRID_SIZE;
export const OVER_LINES = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5] as const;

export type Grid = Float64Array;

export interface Markets {
  home: number;
  draw: number;
  away: number;
  overs: number[];
}

/** Poisson pmf for k = 0..12 by the recurrence p[k] = p[k-1] * lambda / k: one exp, no factorial table. */
function poissonPmf(lambda: number): Float64Array {
  const pmf = new Float64Array(GRID_SIZE);
  let term = Math.exp(-lambda);
  pmf[0] = term;
  for (let k = 1; k < GRID_SIZE; k++) {
    term = (term * lambda) / k;
    pmf[k] = term;
  }
  return pmf;
}

function normalise(grid: Grid): Grid {
  let total = 0;
  for (let i = 0; i < CELLS; i++) total += grid[i] ?? 0;
  for (let i = 0; i < CELLS; i++) grid[i] = (grid[i] ?? 0) / total;
  return grid;
}

function independentGrid(lambdaHome: number, lambdaAway: number): Grid {
  const home = poissonPmf(lambdaHome);
  const away = poissonPmf(lambdaAway);
  const grid = new Float64Array(CELLS);
  for (let i = 0; i < GRID_SIZE; i++) {
    for (let j = 0; j < GRID_SIZE; j++) {
      grid[i * GRID_SIZE + j] = (home[i] ?? 0) * (away[j] ?? 0);
    }
  }
  return grid;
}

/** Pi-rating style: expected goal difference mapped to two Poisson means (hypothesis, ADR-006). */
export function piGrid(lambdaHome: number, lambdaAway: number): Grid {
  return normalise(independentGrid(lambdaHome, lambdaAway));
}

/** Dixon-Coles style: independent Poisson with the tau correction on the four low scores. */
export function dcGrid(lambdaHome: number, lambdaAway: number, rho: number): Grid {
  const grid = independentGrid(lambdaHome, lambdaAway);
  grid[0] = (grid[0] ?? 0) * Math.max(0, 1 - lambdaHome * lambdaAway * rho);
  grid[1] = (grid[1] ?? 0) * Math.max(0, 1 + lambdaHome * rho);
  grid[GRID_SIZE] = (grid[GRID_SIZE] ?? 0) * Math.max(0, 1 + lambdaAway * rho);
  grid[GRID_SIZE + 1] = (grid[GRID_SIZE + 1] ?? 0) * Math.max(0, 1 - rho);
  return normalise(grid);
}

/**
 * Bivariate Poisson (Karlis-Ntzoufras) in convolution form: X = Z1 + Z3, Y = Z2 + Z3 with independent
 * Poisson Z1, Z2, Z3, so P(i, j) = e^-(l1+l2+l3) * sum_k a[i-k] * b[j-k] * c[k], where a, b, c are
 * the un-normalised Poisson terms l^n / n!. Only multiplications and additions per cell.
 */
export function bpGrid(lambda1: number, lambda2: number, lambda3: number): Grid {
  const a = scaledPowers(lambda1);
  const b = scaledPowers(lambda2);
  const c = scaledPowers(lambda3);
  const grid = new Float64Array(CELLS);
  for (let i = 0; i < GRID_SIZE; i++) {
    for (let j = 0; j < GRID_SIZE; j++) {
      const kMax = i < j ? i : j;
      let sum = 0;
      for (let k = 0; k <= kMax; k++) sum += (a[i - k] ?? 0) * (b[j - k] ?? 0) * (c[k] ?? 0);
      grid[i * GRID_SIZE + j] = sum;
    }
  }
  return normalise(grid);
}

/** l^n / n! for n = 0..12 by the recurrence t[n] = t[n-1] * l / n. */
function scaledPowers(lambda: number): Float64Array {
  const terms = new Float64Array(GRID_SIZE);
  terms[0] = 1;
  for (let n = 1; n < GRID_SIZE; n++) terms[n] = ((terms[n - 1] ?? 0) * lambda) / n;
  return terms;
}

/** Weighted linear pool of grids; weights must sum to 1 (section 8.1). */
export function mixGrids(grids: Grid[], weights: number[]): Grid {
  const pooled = new Float64Array(CELLS);
  for (let g = 0; g < grids.length; g++) {
    const grid = grids[g];
    const weight = weights[g] ?? 0;
    if (!grid) continue;
    for (let c = 0; c < CELLS; c++) pooled[c] = (pooled[c] ?? 0) + weight * (grid[c] ?? 0);
  }
  return pooled;
}

/** Every market comes from the one pooled grid (FR-04). */
export function markets(grid: Grid): Markets {
  let home = 0;
  let draw = 0;
  let away = 0;
  const totals = new Float64Array(2 * GRID_SIZE - 1);
  for (let i = 0; i < GRID_SIZE; i++) {
    for (let j = 0; j < GRID_SIZE; j++) {
      const p = grid[i * GRID_SIZE + j] ?? 0;
      if (i > j) home += p;
      else if (i === j) draw += p;
      else away += p;
      totals[i + j] = (totals[i + j] ?? 0) + p;
    }
  }
  const overs = OVER_LINES.map((line) => {
    let over = 0;
    for (let t = Math.floor(line) + 1; t < totals.length; t++) over += totals[t] ?? 0;
    return over;
  });
  return { home, draw, away, overs };
}
