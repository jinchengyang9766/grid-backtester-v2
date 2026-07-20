"use client";

/**
 * `/history/compare?ids=…` — side-by-side stored metrics.
 *
 * The response is rendered exactly as returned, in the requested order. No
 * run is ranked, no winner is marked, and no difference or percentage change
 * is computed: those would be new figures the engine never produced.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { Table, TableScroll, Td, Th } from "@/components/ui/table";
import type { BacktestCompareResponse } from "@/lib/api/backtest-history-types";
import { compareBacktests } from "@/lib/api/backtest-history";
import { ApiClientError } from "@/lib/api/errors";
import { flattenMetrics } from "@/lib/backtests/metrics";
import { EMPTY_VALUE } from "@/lib/datasets/display";

export function CompareResults({ ids }: { ids: number[] }) {
  const [response, setResponse] = useState<BacktestCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const mounted = useRef(true);
  const generation = useRef(0);
  const key = ids.join(",");

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    // The backend requires at least two ids; asking with fewer would be a
    // guaranteed 422, so the request is never made.
    if (ids.length < 2) return;

    const controller = new AbortController();
    const current = ++generation.current;
    let cancelled = false;

    void (async () => {
      try {
        const result = await compareBacktests(ids, controller.signal);
        if (cancelled || !mounted.current || current !== generation.current) return;
        setResponse(result);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (cancelled || !mounted.current || current !== generation.current) return;
        setError(
          caught instanceof ApiClientError
            ? caught.message
            : "Something went wrong. Please try again.",
        );
      } finally {
        if (!cancelled && mounted.current && current === generation.current) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
    // `key` captures the id list; `ids` itself is a fresh array each render.
  }, [key, reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setResponse(null);
    setReloadKey((value) => value + 1);
  }, []);

  const backToHistory = (
    <Link
      href="/history"
      className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
    >
      Back to history
    </Link>
  );

  if (ids.length < 2) {
    return (
      <Alert tone="error" title="Select at least two backtests" action={backToHistory}>
        Comparison needs two or more runs.
      </Alert>
    );
  }

  if (loading) return <LoadingState label="Loading comparison…" />;

  if (error !== null || response === null) {
    return (
      <Alert
        tone="error"
        title="Comparison unavailable"
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={retry}>
              Try again
            </Button>
            {backToHistory}
          </div>
        }
      >
        {error ?? "Backtest not found."}
      </Alert>
    );
  }

  // Union of every metric path, in first-seen order, so the rows are stable
  // and a run missing a metric simply shows a dash.
  const flattened = response.runs.map((run) => flattenMetrics(run.result_metrics));
  const paths: string[] = [];
  for (const map of flattened) {
    for (const path of map.keys()) {
      if (!paths.includes(path)) paths.push(path);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Comparing {response.runs.length} backtests, in the order you selected
          them.
        </p>
        {backToHistory}
      </div>

      {paths.length === 0 ? (
        <Alert tone="info" title="No stored metrics to compare">
          None of the selected runs has a saved result document.
        </Alert>
      ) : (
        <TableScroll label="Backtest comparison">
          <Table caption="Stored result metrics for each selected backtest, side by side">
            <thead>
              <tr>
                <Th>Metric</Th>
                {response.runs.map((run) => (
                  <Th key={run.id}>
                    {run.name} (ID {run.id})
                  </Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paths.map((path) => (
                <tr key={path}>
                  <Th scope="row">{path}</Th>
                  {flattened.map((map, index) => (
                    <Td key={response.runs[index].id} numeric wrap>
                      {map.get(path) ?? EMPTY_VALUE}
                    </Td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
        </TableScroll>
      )}

      <p className="text-xs text-slate-600 dark:text-slate-400">
        Values are shown exactly as stored. No ranking, difference, or
        percentage change is calculated.
      </p>
    </div>
  );
}
