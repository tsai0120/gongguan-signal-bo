"""Synthetic two-phase intersection inspired by Gongguan, Taipei."""

from dataclasses import dataclass

import numpy as np

DURATION = 3600
CLEARANCE = 5
WALK_CLEARANCE = 12
MIN_GREEN = 25
BOUNDS = np.array([[100.0, 160.0], [0.45, 0.65]])
BASELINE = np.array([130.0, 0.55])

# Rates per hour: main-axis buses, pedestrians crossing the main axis,
# main-axis general vehicles, cross-axis general vehicles.
TRAIN = {
    "Typical": (110, 350, 480, 420),
    "Bus surge": (180, 380, 620, 420),
    "Cross-axis surge": (125, 650, 480, 660),
}
HOLDOUT = {
    "Typical": (120, 390, 520, 460),
    "Bus surge": (195, 425, 650, 450),
    "Cross-axis surge": (140, 710, 510, 700),
}


@dataclass(frozen=True)
class Demand:
    buses: np.ndarray
    pedestrians: np.ndarray
    main_vehicles: np.ndarray
    cross_vehicles: np.ndarray


def generate_demands(scenarios, seeds):
    """Pre-generate common arrivals so all candidates face the same demand."""
    demands = {}
    for index, (scenario, rates) in enumerate(scenarios.items()):
        demands[scenario] = []
        for seed in seeds:
            rng = np.random.default_rng([seed, index])
            arrivals = [
                np.sort(rng.uniform(0, DURATION, rng.poisson(rate)))
                for rate in rates
            ]
            if scenario == "Bus surge":
                # Add groups of buses arriving within six seconds of one another.
                starts = rng.uniform(0, DURATION - 6, 12)
                pulses = starts[:, None] + rng.uniform(0, 6, (12, 4))
                arrivals[0] = np.sort(np.concatenate([arrivals[0], pulses.ravel()]))
            demands[scenario].append(Demand(*arrivals))
    return demands


def phase_lengths(plan):
    cycle, share = plan
    distributable = cycle - 2 * (MIN_GREEN + CLEARANCE)
    main = MIN_GREEN + share * distributable
    cross = MIN_GREEN + (1 - share) * distributable
    return cycle, main, cross


def queue_delay(arrivals, cycle, start, green, headway):
    """FIFO queue with fixed service slots, including after arrivals stop."""
    slots_per_cycle = int(np.floor(green / headway))
    cycles = int(np.ceil(DURATION / cycle)) + int(
        np.ceil(len(arrivals) / slots_per_cycle)
    ) + 2
    slots = (
        np.arange(cycles)[:, None] * cycle
        + start
        + np.arange(slots_per_cycle) * headway
    ).ravel()
    earliest = np.searchsorted(slots, arrivals)
    position = np.arange(len(arrivals))
    assigned = np.maximum.accumulate(earliest - position) + position
    return slots[assigned] - arrivals


def simulate(plan, demand):
    cycle, main, cross = phase_lengths(plan)
    cross_start = main + CLEARANCE
    bus_wait = queue_delay(demand.buses, cycle, 0, main, headway=7)
    main_wait = queue_delay(demand.main_vehicles, cycle, 0, main, headway=2)
    cross_wait = queue_delay(
        demand.cross_vehicles, cycle, cross_start, cross, headway=2
    )
    # Pedestrians crossing the main axis can enter during the cross-axis
    # phase, except during its final clearance interval.
    since_walk_start = np.mod(demand.pedestrians - cross_start, cycle)
    pedestrian_wait = np.where(
        since_walk_start < cross - WALK_CLEARANCE, 0, cycle - since_walk_start
    )
    return np.array([
        bus_wait.mean(),
        np.quantile(pedestrian_wait, 0.95),
        np.concatenate([main_wait, cross_wait]).mean(),
    ])


def evaluate(plan, demands):
    """Average each metric across replications within each scenario."""
    return np.array([
        np.mean([simulate(plan, demand) for demand in replications], axis=0)
        for replications in demands.values()
    ])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate one timing plan on training demand.")
    parser.add_argument("--cycle", type=float, default=BASELINE[0], help="Signal period in seconds")
    parser.add_argument("--share", type=float, default=BASELINE[1], help="Main-axis share of free green")
    args = parser.parse_args()
    plan = np.array([args.cycle, args.share])
    if not np.all((BOUNDS[:, 0] <= plan) & (plan <= BOUNDS[:, 1])):
        parser.error("cycle must be 100–160 s and share must be 0.45–0.65")
    _, main, cross = phase_lengths(plan)
    print(f"Main-axis green {main:.1f} s  |  Cross-axis green {cross:.1f} s")
    results = evaluate(plan, generate_demands(TRAIN, range(10, 14)))
    print(f"{'Scenario':<20} {'Bus mean (s)':>14} {'Walk P95 (s)':>14} {'Car mean (s)':>14}")
    for scenario, values in zip(TRAIN, results):
        print(f"{scenario:<20} {values[0]:>14.1f} {values[1]:>14.1f} {values[2]:>14.1f}")
