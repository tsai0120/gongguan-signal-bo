"""Compare average-demand MOBO, worst-scenario MOBO, and random search."""

import argparse
import csv
from pathlib import Path

from botorch.acquisition.multi_objective.logei import (
    qLogNoisyExpectedHypervolumeImprovement,
)
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.models.transforms.outcome import Standardize
from botorch.sampling.normal import SobolQMCNormalSampler
from botorch.utils.multi_objective.hypervolume import Hypervolume
from botorch.utils.multi_objective.pareto import is_non_dominated
from gpytorch.mlls import ExactMarginalLogLikelihood
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import qmc
import torch

from simulator import BASELINE, BOUNDS, HOLDOUT, TRAIN, evaluate, generate_demands

METHODS = ("Mean MOBO", "Robust MOBO", "Random")
COLORS = {"Mean MOBO": "#1d69a5", "Robust MOBO": "#00846b", "Random": "#767480"}
REF = torch.tensor([-150., -150.], dtype=torch.double)
GRID = torch.cartesian_prod(
    torch.linspace(0, 1, 41, dtype=torch.double),
    torch.linspace(0, 1, 41, dtype=torch.double),
)


def scale(unit_plan):
    return BOUNDS[:, 0] + np.asarray(unit_plan) * np.diff(BOUNDS, axis=1).ravel()


def propose(points, scores, seed):
    x = torch.as_tensor(np.array(points), dtype=torch.double)
    y = torch.as_tensor(-np.array(scores), dtype=torch.double)
    model = SingleTaskGP(x, y, outcome_transform=Standardize(m=2))
    fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
    acquisition = qLogNoisyExpectedHypervolumeImprovement(
        model=model, ref_point=REF.tolist(), X_baseline=x,
        sampler=SobolQMCNormalSampler(torch.Size([64]), seed=seed),
        prune_baseline=False,
    )
    candidates = GRID[~torch.isclose(GRID[:, None], x[None]).all(-1).any(-1)]
    with torch.no_grad():
        values = torch.cat([acquisition(chunk[:, None, :]) for chunk in candidates.split(256)])
    return candidates[values.argmax()].numpy()


def hypervolume(scores):
    return Hypervolume(REF).compute(torch.as_tensor(-np.array(scores), dtype=torch.double))


def search(method, seed, budget, train):
    torch.manual_seed(seed)
    initial = qmc.Sobol(d=2, scramble=True, seed=seed).random_base2(m=2)
    rng = np.random.default_rng(seed + 100)
    points, scores, details, robust_hv = [], [], [], []
    for step in range(budget):
        if step < len(initial):
            unit_plan = initial[step]
        elif method == "Random":
            unit_plan = rng.random(2)
        else:
            unit_plan = propose(points, scores, seed * 100 + step)
        result = evaluate(scale(unit_plan), train)
        points.append(unit_plan)
        details.append(result)
        summary = result.mean(axis=0) if method == "Mean MOBO" else result.max(axis=0)
        scores.append(summary[:2])
        # Use the same robust metric to compare all searches.
        robust_hv.append(hypervolume(np.max(details, axis=1)[:, :2]))
    return scale(points), np.array(details), robust_hv


def recommend(plans, details, method):
    # Equal relative weighting against the two fixed reference limits.
    summary = details.mean(axis=1) if method == "Mean MOBO" else details.max(axis=1)
    return plans[np.argmin((summary[:, :2] / -REF.numpy()).sum(axis=1))]


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def plot(path, runs, recommendations, baseline, holdout):
    fig, (history, frontier) = plt.subplots(1, 2, figsize=(10, 3.55), layout="constrained")
    for method in METHODS:
        traces = np.array([run[2] for run in runs[method]])
        steps = np.arange(1, traces.shape[1] + 1)
        history.plot(steps, np.median(traces, axis=0), color=COLORS[method], label=method)
        history.fill_between(steps, traces.min(axis=0), traces.max(axis=0),
                             color=COLORS[method], alpha=0.12)
    history.set(xlabel="Evaluated plans", ylabel="Robust hypervolume (s²)",
                title="Search progress on training scenarios")
    history.legend(frameon=False, fontsize=8)
    plans, training, _ = runs["Robust MOBO"][0]
    holdout_points = np.array([evaluate(plan, holdout).max(axis=0)[:2] for plan in plans])
    mask = is_non_dominated(-torch.as_tensor(training.max(axis=1)[:, :2])).numpy()
    frontier.scatter(*holdout_points.T, color="#c6d1d0", s=21, label="Robust MOBO trials")
    frontier.scatter(*holdout_points[mask].T, facecolors="none", edgecolors=COLORS["Robust MOBO"],
                     s=62, label="Training Pareto plans")
    markers = {"Mean MOBO": "^", "Robust MOBO": "D", "Random": "s"}
    for method, result in recommendations.items():
        frontier.scatter(*result.max(axis=0)[:2], marker=markers[method],
                         color=COLORS[method], s=48, label=method, zorder=4)
    frontier.scatter(*baseline.max(axis=0)[:2], marker="*", color="#c44b36", s=105,
                     label="Fixed baseline", zorder=4)
    frontier.set(xlabel="Worst scenario: mean bus delay (s)",
                 ylabel="Worst scenario: pedestrian P95 (s)",
                 title="Held-out scenarios · first run")
    frontier.legend(frameon=False, fontsize=7, loc="best")
    for ax in (history, frontier):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.18)
        ax.set_axisbelow(True)
    fig.savefig(path, dpi=220)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    if not 4 <= args.budget <= len(GRID) or args.runs < 1:
        parser.error("use a budget between 4 and 1681 and at least one run")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    train = generate_demands(TRAIN, range(10, 14))
    holdout = generate_demands(HOLDOUT, range(100, 112))
    baseline = evaluate(BASELINE, holdout)
    runs = {method: [] for method in METHODS}
    trials, selected, first_run = [], [], {}
    for seed in range(args.runs):
        print(f"Run {seed + 1}/{args.runs}", flush=True)
        for method in ("Fixed baseline", *METHODS):
            if method == "Fixed baseline":
                plan, result = BASELINE, baseline
            else:
                run = search(method, seed, args.budget, train)
                runs[method].append(run)
                plans, details, trace = run
                for step, (candidate, sample, hv) in enumerate(zip(plans, details, trace), 1):
                    for scenario, metrics in zip(TRAIN, sample):
                        trials.append([seed, method, step, *candidate, scenario, *metrics, hv])
                plan = recommend(plans, details, method)
                result = evaluate(plan, holdout)
                if seed == 0:
                    first_run[method] = result
            for scenario, metrics in zip(HOLDOUT, result):
                selected.append([seed, method, *plan, scenario, *metrics])
    metrics = ["mean_bus_delay_s", "pedestrian_p95_wait_s", "mean_general_vehicle_delay_s"]
    plan_columns = ["cycle_s", "main_green_share", "scenario", *metrics]
    write_csv(args.output / "trials.csv",
              ["run", "method", "step", *plan_columns, "training_robust_hv_s2"], trials)
    write_csv(args.output / "holdout.csv", ["run", "method", *plan_columns], selected)
    plot(args.output / "results.png", runs, first_run, baseline, holdout)


if __name__ == "__main__":
    main()
