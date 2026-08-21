from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from experiment_utils import (
    approach_display_label,
    approach_results_dir,
    load_approaches,
    load_approach_labels,
    read_runs_csv,
    selected_approaches,
    use_case_display_label,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze runner-level overhead metrics.")
    parser.add_argument("--approach", default="all", help="Approach name or 'all'.")
    parser.add_argument(
        "--use-case",
        help="Filter approaches by use case suffix, for example 'perceptron_gridsearch'.",
    )
    parser.add_argument(
        "--baseline",
        help=(
            "Baseline approach name used for overhead percentage. "
            "Defaults to baseline_<use-case> when --use-case is provided, otherwise baseline."
        ),
    )
    parser.add_argument(
        "--run-scope",
        choices=["latest_batch", "latest_n", "all"],
        default="latest_batch",
        help=(
            "Which rows from runs.csv to analyze. latest_batch uses rows from the last run_001 onward, "
            "which avoids mixing old executions because runs.csv is append-only."
        ),
    )
    parser.add_argument(
        "--latest-runs",
        type=int,
        help="Number of latest rows to keep when --run-scope latest_n is used.",
    )
    parser.add_argument(
        "--exclude-baseline",
        action="store_true",
        help="Exclude the baseline row from the markdown/csv table.",
    )
    parser.add_argument(
        "--output-prefix",
        default="analysis_1_overhead",
        help="Output filename prefix under experiments/results/_analysis.",
    )
    return parser.parse_args()


def selected_names(approach_name: str, use_case: str | None) -> list[str]:
    if approach_name != "all":
        return list(selected_approaches(approach_name))

    _, approaches = load_approaches()
    names = []
    for name, approach in approaches.items():
        if not approach.get("uses_flowcept", True):
            continue
        if use_case and not name.endswith(f"_{use_case}"):
            continue
        if not use_case and not approach.get("enabled", False):
            continue
        if not read_runs_csv(name):
            continue
        names.append(name)
    return names


def default_baseline(use_case: str | None) -> str:
    return f"baseline_{use_case}" if use_case else "baseline"


def latest_batch(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return rows
    start = 0
    for index, row in enumerate(rows):
        if row.get("run_id") == "run_001" or row.get("run_index") == "1":
            start = index
    return rows[start:]


def select_run_rows(
    rows: list[dict[str, str]],
    run_scope: str,
    latest_runs: int | None,
) -> list[dict[str, str]]:
    if run_scope == "all":
        return rows
    if run_scope == "latest_n":
        if latest_runs is None:
            raise SystemExit("--latest-runs is required when --run-scope latest_n is used.")
        return rows[-latest_runs:]
    return latest_batch(rows)


def numeric(rows: list[dict[str, str]], field: str) -> list[float]:
    out = []
    for row in rows:
        value = row.get(field, "")
        if value == "":
            continue
        out.append(float(value))
    return out


def summarize_values(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "stdev": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize_approach(
    name: str,
    labels: dict,
    run_scope: str,
    latest_runs: int | None,
) -> dict:
    rows = read_runs_csv(name)
    selected_rows = select_run_rows(rows, run_scope, latest_runs)
    runtime = numeric(selected_rows, "runtime_seconds")
    success_count = sum(1 for r in selected_rows if str(r.get("success")).lower() == "true")
    timeout_count = sum(1 for r in selected_rows if str(r.get("timed_out")).lower() == "true")
    summary = {
        "approach": name,
        "approach_label": approach_display_label(name, labels),
        "use_case_label": use_case_display_label(name, labels),
        "run_scope": run_scope,
        "selected_run_count": len(selected_rows),
        "run_count": len(selected_rows),
        "success_count": success_count,
        "failure_count": len(selected_rows) - success_count,
        "timeout_count": timeout_count,
        "runtime_seconds": summarize_values(runtime),
        "stdout_bytes": summarize_values(numeric(selected_rows, "stdout_bytes")),
        "stderr_bytes": summarize_values(numeric(selected_rows, "stderr_bytes")),
        "workflow_count_delta": summarize_values(numeric(selected_rows, "workflow_count_delta")),
        "task_count_delta": summarize_values(numeric(selected_rows, "task_count_delta")),
        "object_count_delta": summarize_values(numeric(selected_rows, "object_count_delta")),
        "new_task_count": summarize_values(numeric(selected_rows, "new_task_count")),
        "memory_peak_rss_bytes": summarize_values(numeric(selected_rows, "memory_peak_rss_bytes")),
        "memory_mean_rss_bytes": summarize_values(numeric(selected_rows, "memory_mean_rss_bytes")),
        "cpu_time_total_seconds": summarize_values(numeric(selected_rows, "cpu_time_total_seconds")),
        "cpu_time_per_wall_second": summarize_values(numeric(selected_rows, "cpu_time_per_wall_second")),
        "cpu_utilization_percent_max": summarize_values(numeric(selected_rows, "cpu_utilization_percent_max")),
        "cpu_utilization_percent_mean": summarize_values(numeric(selected_rows, "cpu_utilization_percent_mean")),
    }
    return summary


def fmt_bytes(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value / (1024 * 1024):.2f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def relative_runtime_percent(mean: float | None, baseline_mean: float | None) -> float | None:
    if baseline_mean is None or mean is None:
        return None
    return ((mean - baseline_mean) / baseline_mean) * 100


def write_markdown(path: Path, summaries: list[dict], baseline_mean: float | None, use_case: str | None) -> None:
    use_cases = sorted({str(row["use_case_label"]) for row in summaries})
    run_scopes = sorted({str(row["run_scope"]) for row in summaries})
    lines = [
        "# Analysis 1: Execution Overhead",
        "",
        f"Use case: {', '.join(use_cases) if use_cases else use_case or 'n/a'}",
        f"Run scope: {', '.join(run_scopes) if run_scopes else 'n/a'}",
        "",
        "| Approach | Runs | Success | Mean Runtime (s) | Median Runtime (s) | Runtime Stdev (s) | Runtime Difference from Baseline (%) | Mean Peak RSS (MiB) | Mean CPU Time (s) | Mean CPU Time / Wall Time | Mean Number of Flowcept Tasks |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        rt = s["runtime_seconds"]
        mean = rt["mean"]
        overhead = relative_runtime_percent(mean, baseline_mean)
        lines.append(
            "| {approach} | {runs} | {success} | {mean} | {median} | {stdev} | {overhead} | {peak_rss} | {cpu_time} | {cpu_wall} | {tasks} |".format(
                approach=s["approach_label"],
                runs=s["run_count"],
                success=s["success_count"],
                mean="" if mean is None else f"{mean:.6f}",
                median="" if rt["median"] is None else f"{rt['median']:.6f}",
                stdev="" if rt["stdev"] is None else f"{rt['stdev']:.6f}",
                overhead=format_percent(overhead),
                peak_rss=fmt_bytes(s["memory_peak_rss_bytes"]["mean"]),
                cpu_time="" if s["cpu_time_total_seconds"]["mean"] is None else f"{s['cpu_time_total_seconds']['mean']:.6f}",
                cpu_wall="" if s["cpu_time_per_wall_second"]["mean"] is None else f"{s['cpu_time_per_wall_second']['mean']:.3f}",
                tasks="" if s["new_task_count"]["mean"] is None else f"{s['new_task_count']['mean']:.2f}",
            )
        )
    lines.extend(
        [
            "",
            "## Metric Notes",
            "",
            "- **Mean runtime (s):** wall-clock execution time measured by the experiment runner for the whole approach process.",
            "- **Runtime Difference from Baseline (%):** percentage difference between the approach mean runtime and the baseline mean runtime. Positive values mean slower than baseline; negative values mean faster.",
            "- **Runs:** selected rows from each append-only `runs.csv`; by default only the latest batch is used.",
            "- **Peak RSS mean (MiB):** mean, across runs, of each run's peak resident set size. RSS is the amount of physical RAM currently resident for the observed process tree.",
            "- **CPU time mean (s):** mean accumulated CPU time for the observed process tree. This can be greater than wall-clock time when multiple cores/processes run in parallel.",
            "- **Mean CPU Time / Wall Time:** mean ratio of CPU time to wall-clock runtime. Values above 1 indicate parallel CPU usage across multiple cores/processes.",
            "- **Mean Number of Flowcept Tasks:** mean number of new Flowcept TaskObject records observed in the approach database per run.",
            "",
            "Resource metrics are collected externally by the runner using local process-tree sampling. They include the launched approach process and child processes visible to the local OS. In truly distributed executions where workers run on remote nodes, these runner-level CPU and memory metrics will not capture remote worker resource usage; use Flowcept task telemetry or cluster-level monitoring for that case.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    labels = load_approach_labels()
    baseline_name = args.baseline or default_baseline(args.use_case)
    names = selected_names(args.approach, args.use_case)

    analysis_names = names
    if read_runs_csv(baseline_name):
        if baseline_name not in analysis_names:
            analysis_names = [baseline_name, *analysis_names]

    summaries = [summarize_approach(name, labels, args.run_scope, args.latest_runs) for name in analysis_names]
    baseline_summary = next((s for s in summaries if s["approach"] == baseline_name), None)
    baseline_mean = None
    if baseline_summary:
        baseline_mean = baseline_summary["runtime_seconds"]["mean"]
    if args.exclude_baseline:
        summaries = [s for s in summaries if s["approach"] != baseline_name]

    output_root = approach_results_dir("_analysis")
    output_root.mkdir(parents=True, exist_ok=True)
    output_prefix = args.output_prefix
    if args.use_case and output_prefix == "analysis_1_overhead":
        output_prefix = f"analysis_1_overhead_{args.use_case}"
    write_json(output_root / f"{output_prefix}.json", summaries)
    write_markdown(output_root / f"{output_prefix}.md", summaries, baseline_mean, args.use_case)

    csv_path = output_root / f"{output_prefix}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "approach",
                "approach_label",
                "use_case_label",
                "run_scope",
                "selected_run_count",
                "run_count",
                "success_count",
                "failure_count",
                "mean_runtime_seconds",
                "median_runtime_seconds",
                "stdev_runtime_seconds",
                "runtime_difference_from_baseline_percent",
                "mean_memory_peak_rss_bytes",
                "mean_memory_peak_rss_mib",
                "mean_memory_mean_rss_bytes",
                "mean_cpu_time_total_seconds",
                "mean_cpu_time_per_wall_second",
                "mean_cpu_utilization_percent_max",
                "mean_cpu_utilization_percent_mean",
                "mean_new_task_count",
            ],
        )
        writer.writeheader()
        for s in summaries:
            mean = s["runtime_seconds"]["mean"]
            runtime_diff = relative_runtime_percent(mean, baseline_mean)
            writer.writerow(
                {
                    "approach": s["approach"],
                    "approach_label": s["approach_label"],
                    "use_case_label": s["use_case_label"],
                    "run_scope": s["run_scope"],
                    "selected_run_count": s["selected_run_count"],
                    "run_count": s["run_count"],
                    "success_count": s["success_count"],
                    "failure_count": s["failure_count"],
                    "mean_runtime_seconds": mean,
                    "median_runtime_seconds": s["runtime_seconds"]["median"],
                    "stdev_runtime_seconds": s["runtime_seconds"]["stdev"],
                    "runtime_difference_from_baseline_percent": "" if runtime_diff is None else runtime_diff,
                    "mean_memory_peak_rss_bytes": s["memory_peak_rss_bytes"]["mean"],
                    "mean_memory_peak_rss_mib": (
                        s["memory_peak_rss_bytes"]["mean"] / (1024 * 1024)
                        if s["memory_peak_rss_bytes"]["mean"] is not None
                        else ""
                    ),
                    "mean_memory_mean_rss_bytes": s["memory_mean_rss_bytes"]["mean"],
                    "mean_cpu_time_total_seconds": s["cpu_time_total_seconds"]["mean"],
                    "mean_cpu_time_per_wall_second": s["cpu_time_per_wall_second"]["mean"],
                    "mean_cpu_utilization_percent_max": s["cpu_utilization_percent_max"]["mean"],
                    "mean_cpu_utilization_percent_mean": s["cpu_utilization_percent_mean"]["mean"],
                    "mean_new_task_count": s["new_task_count"]["mean"],
                }
            )

    print(f"Wrote {output_root / f'{output_prefix}.md'}")


if __name__ == "__main__":
    main()
