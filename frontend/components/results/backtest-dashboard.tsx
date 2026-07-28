"use client";

/**
 * The persisted-result dashboard.
 *
 * Everything shown comes from the detail response: the stored
 * `result_metrics` document, the canonical configuration, and the four
 * normalized series. Nothing is recomputed, and a run with null metrics says
 * so rather than showing invented figures.
 */

import { BenchmarkComparisonChart } from "@/components/charts/benchmark-comparison-chart";
import { DrawdownChart } from "@/components/charts/drawdown-chart";
import { EquityChart } from "@/components/charts/equity-chart";
import { NormalizedPerformanceChart } from "@/components/charts/normalized-performance-chart";
import { PriceGridChart } from "@/components/charts/price-grid-chart";
import { PriceTradesChart } from "@/components/charts/price-trades-chart";
import { TradeActivityChart } from "@/components/charts/trade-activity-chart";
import { ConfigurationSummary } from "@/components/results/configuration-summary";
import { MetricGrid, MetricSectionBlock } from "@/components/results/metric-grid";
import {
  DailyEquityTable,
  EventEquityTable,
  TradesTable,
  ZoneEventsTable,
} from "@/components/results/result-tables";
import { ResultTabs, type TabDefinition } from "@/components/results/result-tabs";
import { Alert } from "@/components/ui/alert";
import type { BacktestDetailWithSeries } from "@/lib/api/backtest-history-types";
import {
  additionalRows,
  benchmarkSections,
  benchmarkTwoDayOneSection,
  costSection,
  finalStateSection,
  firstReturnSection,
  gridGeometrySection,
  headlineRows,
  strategySection,
  zoneSection,
} from "@/lib/backtests/metrics";
import { dataModeLabel, dateRangeLabel, displayText, timestampLabel } from "@/lib/datasets/display";

function MetricsUnavailable({ status }: { status: string }) {
  return (
    <Alert tone="info" title="No result metrics are stored for this run">
      {status === "FAILED"
        ? "The run did not complete, so the engine produced no metrics. The configuration and dataset it attempted are shown below."
        : "This run has not produced results yet. Its configuration and dataset are shown below."}
    </Alert>
  );
}

/**
 * One titled band of related charts.
 *
 * Each band is a labelled section, so the charts tab is a short list of
 * landmarks a screen reader or keyboard user can move between rather than one
 * undifferentiated wall of figures.
 */
function ChartGroup({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="space-y-4">
      <div className="space-y-0.5 border-b border-slate-200 pb-2 dark:border-slate-700">
        <h3 id={id} className="text-sm font-semibold">
          {title}
        </h3>
        <p className="text-xs text-slate-600 dark:text-slate-400">{description}</p>
      </div>
      <div className="space-y-8">{children}</div>
    </section>
  );
}

export function BacktestDashboard({ detail }: { detail: BacktestDetailWithSeries }) {
  const metrics = detail.result_metrics;
  const hasMetrics = metrics !== null;
  const trades = detail.trades ?? [];
  const zoneEvents = detail.zone_events ?? [];
  const dailyEquity = detail.daily_equity ?? [];
  const eventEquity = detail.event_equity ?? [];

  const extraRows = additionalRows(metrics);
  const dayOne = benchmarkTwoDayOneSection(metrics);

  const tabs: TabDefinition[] = [
    {
      id: "overview",
      label: "Overview",
      render: () => (
        <div className="space-y-6">
          {hasMetrics ? (
            <>
              {/* Named so the block is a navigable landmark: several of these
                  figures are repeated verbatim in the full metric sections. */}
              <section aria-labelledby="headline-figures" className="space-y-2">
                <h3 id="headline-figures" className="text-sm font-semibold">
                  Headline figures
                </h3>
                <MetricGrid rows={headlineRows(metrics)} />
              </section>
              <MetricSectionBlock section={strategySection(metrics)} />
              <MetricSectionBlock section={finalStateSection(metrics)} />
              <MetricSectionBlock section={firstReturnSection(metrics)} />
            </>
          ) : (
            <MetricsUnavailable status={detail.status} />
          )}
        </div>
      ),
    },
    {
      id: "charts",
      label: "Charts",
      render: () => (
        <div className="space-y-10">
          <ChartGroup
            id="charts-price"
            title="Price and trades"
            description="Where the price went, and where the engine actually bought and sold."
          >
            <PriceTradesChart
              dailyEquity={dailyEquity}
              trades={trades}
              metrics={metrics}
            />
            <PriceGridChart dailyEquity={dailyEquity} metrics={metrics} />
          </ChartGroup>

          <ChartGroup
            id="charts-performance"
            title="Equity and performance"
            description="How the portfolio grew, and how that compares with holding instead of trading."
          >
            <EquityChart dailyEquity={dailyEquity} metrics={metrics} />
            <BenchmarkComparisonChart dailyEquity={dailyEquity} metrics={metrics} />
            <NormalizedPerformanceChart dailyEquity={dailyEquity} metrics={metrics} />
          </ChartGroup>

          <ChartGroup
            id="charts-risk"
            title="Risk and activity"
            description="How far the portfolio fell below its peak, and when it traded."
          >
            <DrawdownChart dailyEquity={dailyEquity} />
            <TradeActivityChart
              dailyEquity={dailyEquity}
              trades={trades}
              metrics={metrics}
            />
          </ChartGroup>

          <p className="text-xs text-slate-600 dark:text-slate-400">
            Charts are drawn from the stored result rows. The exact values are
            listed in the series tables.
          </p>
        </div>
      ),
    },
    {
      id: "benchmarks",
      label: "Benchmarks",
      render: () =>
        hasMetrics ? (
          <div className="space-y-6">
            {benchmarkSections(metrics).map((section) => (
              <MetricSectionBlock key={section.title} section={section} />
            ))}
            {dayOne && <MetricSectionBlock section={dayOne} />}
          </div>
        ) : (
          <MetricsUnavailable status={detail.status} />
        ),
    },
    {
      id: "costs",
      label: "Costs & zones",
      render: () =>
        hasMetrics ? (
          <div className="space-y-6">
            <MetricSectionBlock section={costSection(metrics)} />
            <MetricSectionBlock section={zoneSection(metrics)} />
          </div>
        ) : (
          <MetricsUnavailable status={detail.status} />
        ),
    },
    {
      id: "configuration",
      label: "Configuration",
      render: () => (
        <div className="space-y-6">
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Dataset</h3>
            <MetricGrid
              rows={[
                { label: "Dataset", value: `${detail.dataset.name} (ID ${detail.dataset.id})` },
                { label: "Security name", value: displayText(detail.dataset.security_name) },
                { label: "Security code", value: displayText(detail.dataset.security_code) },
                { label: "Source type", value: detail.dataset.source_type },
                { label: "Original filename", value: detail.dataset.original_filename },
                { label: "Data mode", value: dataModeLabel(detail.dataset.data_mode) },
                {
                  label: "Dataset range",
                  value: dateRangeLabel(detail.dataset.start_date, detail.dataset.end_date),
                },
                { label: "Rows", value: String(detail.dataset.row_count) },
                {
                  label: "Backtest range",
                  value: dateRangeLabel(detail.start_date, detail.end_date),
                },
              ]}
            />
          </section>

          <ConfigurationSummary
            configuration={detail.configuration}
            dataMode={detail.dataset.data_mode}
          />

          {hasMetrics && <MetricSectionBlock section={gridGeometrySection(metrics)} />}

          {extraRows.length > 0 && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Additional stored values</h3>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Values present in the saved result that this version does not
                have a dedicated label for.
              </p>
              <MetricGrid rows={extraRows} />
            </section>
          )}
        </div>
      ),
    },
    {
      id: "series",
      label: "Result tables",
      render: () => (
        <div className="space-y-8">
          <TradesTable rows={trades} />
          <ZoneEventsTable rows={zoneEvents} />
          <DailyEquityTable rows={dailyEquity} />
          <EventEquityTable rows={eventEquity} />
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {detail.status === "FAILED" && detail.error_message !== null && (
        <Alert tone="error" title="This run did not complete">
          <p className="break-words">{detail.error_message}</p>
        </Alert>
      )}
      {(detail.status === "PENDING" || detail.status === "RUNNING") && (
        <Alert tone="info" title={`This run is ${detail.status.toLowerCase()}`}>
          Result data is not available yet.
        </Alert>
      )}

      <dl className="grid gap-x-6 gap-y-1.5 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        {(
          [
            ["Backtest ID", String(detail.id)],
            ["Dataset", detail.dataset.name],
            ["Created", timestampLabel(detail.created_at)],
            ["Completed", detail.completed_at ? timestampLabel(detail.completed_at) : "—"],
          ] as [string, string][]
        ).map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      <ResultTabs tabs={tabs} />
    </div>
  );
}
