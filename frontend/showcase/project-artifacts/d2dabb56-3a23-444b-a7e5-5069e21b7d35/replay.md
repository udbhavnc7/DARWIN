# Replay this Real Project Mode evaluation

- Evaluation: `d2dabb56-3a23-444b-a7e5-5069e21b7d35`
- Adapter: `sanchay-reporting-v1` version `1.0.0`
- Source: https://github.com/udbhavnc7/Sanchay at `7e1bc4cdd31e53380e7896b4a20a864bbebcee1e`
- Mode: `quick`

## API replay

```powershell
$body = @{ inspection_id = "11fe42c2-927d-44bc-9b7e-bc4e4e021f32"; adapter_id = "sanchay-reporting-v1"; mode = "quick"; consent = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post -ContentType application/json -Body $body
```

The source is fetched read-only at the pinned commit. DARWIN never edits, commits or pushes it.

## Candidate diff

```diff
--- a/web/src/utils/reportBundle.ts
+++ b/web/src/utils/reportBundle.ts
@@ -0,0 +1,120 @@
+/**
+ * Candidate: shared single-pass report aggregation.
+ *
+ * This module is placed in an isolated Sanchay overlay and re-exported from the
+ * real `utils/reporting.ts`. `ReportsTab.tsx` is patched to call it instead of
+ * traversing the same currency-scoped ledger three times.
+ *
+ * Semantics deliberately mirror Sanchay's existing functions:
+ * - only Completed transactions contribute;
+ * - transfers are excluded from spending and payees, but completed goal debits count as saved;
+ * - refunds reduce spending and their category, and reduce an existing payee total;
+ * - income credits do not create category or payee rows;
+ * - category/payee ordering and filters are unchanged;
+ * - money is rounded through Sanchay's minor-unit helpers.
+ */
+import type { Currency, Transaction } from '../types/finance';
+import { addMoney, subtractMoney, sumMoney } from './money';
+
+export interface ReportTotals {
+  income: number;
+  spending: number;
+  saved: number;
+  net: number;
+}
+
+export interface CategorySlice {
+  category: string;
+  amount: number;
+  pct: number;
+}
+
+export interface PayeeSlice {
+  name: string;
+  amount: number;
+  count: number;
+}
+
+export interface ReportBundle {
+  totals: ReportTotals;
+  categories: CategorySlice[];
+  payees: PayeeSlice[];
+}
+
+export function computeReportBundle(
+  transactions: readonly Transaction[],
+  currency: Currency = 'INR',
+  payeeLimit = 5
+): ReportBundle {
+  let income = 0;
+  let spending = 0;
+  let saved = 0;
+  const categorySpending = new Map<string, number>();
+  const payeeTotals = new Map<string, { amount: number; count: number }>();
+
+  transactions.forEach((tx) => {
+    if (tx.status !== 'Completed') return;
+
+    if (tx.kind === 'transfer') {
+      if (tx.goalId && tx.type === 'debit') saved = addMoney(saved, tx.amount, currency);
+      return;
+    }
+
+    if (tx.kind === 'refund') {
+      spending = subtractMoney(spending, tx.amount, currency);
+      categorySpending.set(
+        tx.category,
+        subtractMoney(categorySpending.get(tx.category) ?? 0, tx.amount, currency)
+      );
+    } else if (tx.type === 'credit') {
+      income = addMoney(income, tx.amount, currency);
+    } else {
+      spending = addMoney(spending, tx.amount, currency);
+      categorySpending.set(
+        tx.category,
+        addMoney(categorySpending.get(tx.category) ?? 0, tx.amount, currency)
+      );
+    }
+
+    const name = tx.counterparty ?? tx.title;
+    const current = payeeTotals.get(name);
+    if (tx.type === 'debit') {
+      payeeTotals.set(name, {
+        amount: addMoney(current?.amount ?? 0, tx.amount, currency),
+        count: (current?.count ?? 0) + 1,
+      });
+    } else if ((tx.kind === 'refund' || tx.refundOfId) && current) {
+      payeeTotals.set(name, {
+        amount: subtractMoney(current.amount, tx.amount, currency),
+        count: current.count,
+      });
+    }
+  });
+
+  const categoryEntries = Array.from(categorySpending.entries()).filter(([, amount]) => amount > 0);
+  const categoryTotal = sumMoney(categoryEntries.map(([, amount]) => amount), currency);
+  const categories = categoryEntries
+    .map(([category, amount]) => ({
+      category,
+      amount,
+      pct: categoryTotal > 0 ? Math.round((amount / categoryTotal) * 100) : 0,
+    }))
+    .sort((a, b) => b.amount - a.amount);
+
+  const payees = Array.from(payeeTotals.entries())
+    .filter(([, value]) => value.amount > 0)
+    .map(([name, value]) => ({ name, ...value }))
+    .sort((a, b) => b.amount - a.amount)
+    .slice(0, payeeLimit);
+
+  return {
+    totals: {
+      income,
+      spending,
+      saved,
+      net: subtractMoney(subtractMoney(income, spending, currency), saved, currency),
+    },
+    categories,
+    payees,
+  };
+}
--- a/web/src/utils/reporting.ts
+++ b/web/src/utils/reporting.ts
@@ -241,3 +241,7 @@
   });
   return [header.map(csvCell).join(','), ...rows].join('\r\n');
 }
+
+// Real Project Mode candidate: shared single-pass report aggregation.
+export { computeReportBundle } from './reportBundle';
+export type { ReportBundle } from './reportBundle';
--- a/web/src/components/ReportsTab.tsx
+++ b/web/src/components/ReportsTab.tsx
@@ -31,9 +31,7 @@
 import {
   DEFAULT_CURRENCY,
   buildStatementCsv,
-  computeCategoryBreakdown,
-  computePayeeBreakdown,
-  computeReportTotals,
+  computeReportBundle,
   reportCurrencies,
   reportsAccountMap,
   scopeToCurrency,
@@ -118,10 +116,12 @@
     [transactions, accountsById, activeCurrency]
   );
 
-  const totals = useMemo(
-    () => computeReportTotals(inCurrency, activeCurrency),
+  const reportBundle = useMemo(
+    () => computeReportBundle(inCurrency, activeCurrency),
     [inCurrency, activeCurrency]
   );
+
+  const totals = reportBundle.totals;
 
   const comparison = useMemo(() => buildMonthlyComparison(allInCurrency), [allInCurrency]);
 
@@ -149,16 +149,13 @@
 
   const categories = useMemo(
     () =>
-      computeCategoryBreakdown(inCurrency, activeCurrency)
+      reportBundle.categories
         .slice(0, 6)
         .map((row, index) => ({ ...row, color: CHART_COLORS[index % CHART_COLORS.length] })),
-    [inCurrency, activeCurrency]
+    [reportBundle]
   );
 
-  const payees = useMemo(
-    () => computePayeeBreakdown(inCurrency, activeCurrency),
-    [inCurrency, activeCurrency]
-  );
+  const payees = reportBundle.payees;
 
   const trend = useMemo(() => {
     const months = Array.from({ length: 6 }, (_, index) => {

```
