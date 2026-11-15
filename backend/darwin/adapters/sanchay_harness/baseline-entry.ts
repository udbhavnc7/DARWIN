// Baseline benchmark entry.
//
// This imports Sanchay's real reporting functions. The only transformation applied
// when preparing this harness is adding `.ts` extensions to relative module
// specifiers so Node's native TypeScript loader can resolve the same source.
import {
  computeCategoryBreakdown,
  computePayeeBreakdown,
  computeReportTotals,
} from './source/reporting.ts';

export function runBaseline(transactions, currency, payeeLimit = 5) {
  return {
    totals: computeReportTotals(transactions, currency),
    categories: computeCategoryBreakdown(transactions, currency),
    payees: computePayeeBreakdown(transactions, currency, payeeLimit),
  };
}
