from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from experiment_utils import approach_results_dir, read_runs_csv, selected_approaches, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze runner-level overhead metrics.")
    parser.add_argument("--approach", required=True, help="Approach name or 'all'.")
    parser.add_argument(
        "--baseline",
        default="baseline",
        help="Baseline approach name used for overhead percentage when available.",
    )
    return parser.parse_args()


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


def summarize_approach(name: str) -> dict:
    rows = read_runs_csv(name)
    runtime = numeric(rows, "runtime_seconds")
    success_count = sum(1 for r in rows if str(r.get("success")).lower() == "true")
    timeout_count = sum(1 for r in rows if str(r.get("timed_out")).lower() == "true")
    summary = {
        "approach": name,
        "run_count": len(rows),
        "success_count": success_count,
        "failure_count": len(rows) - success_count,
        "timeout_count": timeout_count,
        "runtime_seconds": summarize_values(runtime),
        "stdout_bytes": summarize_values(numeric(rows, "stdout_bytes")),
        "stderr_bytes": summarize_values(numeric(rows, "stderr_bytes")),
        "workflow_count_delta": summarize_values(numeric(rows, "workflow_count_delta")),
        "task_count_delta": summarize_values(numeric(rows, "task_count_delta")),
        "object_count_delta": summarize_values(numeric(rows, "object_count_delta")),
        "new_task_count": summarize_values(numeric(rows, "new_task_count")),
        "memory_peak_rss_bytes": summarize_values(numeric(rows, "memory_peak_rss_bytes")),
        "memory_mean_rss_bytes": summarize_values(numeric(rows, "memory_mean_rss_bytes")),
        "cpu_time_total_seconds": summarize_values(numeric(rows, "cpu_time_total_seconds")),
        "cpu_time_per_wall_second": summarize_values(numeric(rows, "cpu_time_per_wall_second")),
        "cpu_utilization_percent_max": summarize_values(numeric(rows, "cpu_utilization_percent_max")),
        "cpu_utilization_percent_mean": summarize_values(numeric(rows, "cpu_utilization_percent_mean")),
    }
    return summary


def fmt_bytes(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value / (1024 * 1024):.2f}"


def write_markdown(path: Path, summaries: list[dict], baseline_mean: float | None) -> None:
    lines = [
        "# Analysis 1: Execution Overhead",
        "",
        "| Approach | Runs | Success | Mean runtime (s) | Median (s) | Stdev (s) | Overhead vs baseline | Peak RSS mean (MiB) | CPU time mean (s) | CPU/wall mean | Mean new tasks |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        rt = s["runtime_seconds"]
        mean = rt["mean"]
        overhead = ""
        if baseline_mean and mean is not None:
            overhead = f"{((mean - baseline_mean) / baseline_mean) * 100:.2f}%"
        lines.append(
            "| {approach} | {runs} | {success} | {mean} | {median} | {stdev} | {overhead} | {peak_rss} | {cpu_time} | {cpu_wall} | {tasks} |".format(
                approach=s["approach"],
                runs=s["run_count"],
                success=s["success_count"],
                mean="" if mean is None else f"{mean:.6f}",
                median="" if rt["median"] is None else f"{rt['median']:.6f}",
                stdev="" if rt["stdev"] is None else f"{rt['stdev']:.6f}",
                overhead=overhead,
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
            "- **Peak RSS mean (MiB):** mean, across runs, of each run's peak resident set size. RSS is the amount of physical RAM currently resident for the observed process tree.",
            "- **CPU time mean (s):** mean accumulated CPU time for the observed process tree. This can be greater than wall-clock time when multiple cores/processes run in parallel.",
            "- **CPU/wall mean:** mean ratio of CPU time to wall-clock runtime. Values above 1 indicate parallel CPU usage across multiple cores/processes.",
            "- **Mean new tasks:** mean number of new Flowcept TaskObject records observed in the approach database per run.",
            "",
            "Resource metrics are collected externally by the runner using local process-tree sampling. They include the launched approach process and child processes visible to the local OS. In truly distributed executions where workers run on remote nodes, these runner-level CPU and memory metrics will not capture remote worker resource usage; use Flowcept task telemetry or cluster-level monitoring for that case.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = parse_args()
    approaches = selected_approaches(args.approach)
    names = list(approaches)
    if args.baseline not in names and read_runs_csv(args.baseline):
        names = [args.baseline, *names]

    summaries = [summarize_approach(name) for name in names]
    baseline_summary = next((s for s in summaries if s["approach"] == args.baseline), None)
    baseline_mean = None
    if baseline_summary:
        baseline_mean = baseline_summary["runtime_seconds"]["mean"]

    output_root = approach_results_dir("_analysis")
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "analysis_1_overhead.json", summaries)
    write_markdown(output_root / "analysis_1_overhead.md", summaries, baseline_mean)

    csv_path = output_root / "analysis_1_overhead.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "approach",
                "run_count",
                "success_count",
                "failure_count",
                "mean_runtime_seconds",
                "median_runtime_seconds",
                "stdev_runtime_seconds",
                "overhead_vs_baseline_percent",
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
            writer.writerow(
                {
                    "approach": s["approach"],
                    "run_count": s["run_count"],
                    "success_count": s["success_count"],
                    "failure_count": s["failure_count"],
                    "mean_runtime_seconds": mean,
                    "median_runtime_seconds": s["runtime_seconds"]["median"],
                    "stdev_runtime_seconds": s["runtime_seconds"]["stdev"],
                    "overhead_vs_baseline_percent": (
                        ((mean - baseline_mean) / baseline_mean) * 100
                        if baseline_mean and mean is not None
                        else ""
                    ),
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

    print(f"Wrote {output_root / 'analysis_1_overhead.md'}")


if __name__ == "__main__":
    main()
