// Candidate benchmark entry.
//
// The import goes through the modified Sanchay `reporting.ts` call-site module,
// not a private test helper. `ReportsTab.tsx` is patched to call the same export.
import { computeReportBundle } from './candidate-web/src/utils/reporting.ts';

export function runCandidate(transactions, currency, payeeLimit = 5) {
  return computeReportBundle(transactions, currency, payeeLimit);
}
