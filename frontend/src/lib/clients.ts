// The client ledger (Jobs → Clients): one row per client, from the engine's job log.

export type ClientRow = {
  client: string; designs: number; approved: number; rejected: number; waiting: number;
  meters: number; quoted: number; approved_meters: number; approved_quoted: number;
  repeat_orders: number; repeat_meters: number; repeat_quoted: number;
  business: number; last: string; own_rates: boolean;
};

/** The periods the ledger offers, in days. */
export const PERIODS: [number, string][] = [[30, '30 days'], [90, '3 months'], [365, '1 year']];
