"""Run huge numbers of simulations in batches without keeping them all in memory.

Each batch of simulated results is folded into running totals (sums and
score histograms), so a million simulations use the same memory as fifty
thousand. Percentiles are read off the histograms, accurate to the bin width.
"""

from __future__ import annotations

from typing import Callable, Iterator

import numpy as np

BATCH = 50_000
Progress = Callable[[float], None] | None


def batches(n_total: int, seed: int | None, batch: int = BATCH) -> Iterator[tuple[int, int]]:
    """Yield (batch size, batch seed) pairs that add up to ``n_total``."""
    rng = np.random.default_rng(seed)
    done = 0
    while done < n_total:
        size = min(batch, n_total - done)
        yield size, int(rng.integers(0, 2**32))
        done += size


class Tally:
    """Running mean and percentiles for each column of a stream of (rows, columns) batches."""

    def __init__(self, n_cols: int, lo: float = -15.0, hi: float = 100.0, step: float = 0.25):
        self.lo, self.step = lo, step
        self.n_bins = int(round((hi - lo) / step)) + 1
        self.n_cols = n_cols
        self.count = 0
        self.total = np.zeros(n_cols)
        self.hist = np.zeros((n_cols, self.n_bins), dtype=np.int64)

    def add(self, batch: np.ndarray) -> None:
        rows = batch.shape[0]
        self.count += rows
        self.total += batch.sum(axis=0, dtype=np.float64)
        bins = np.clip(np.rint((batch - self.lo) / self.step).astype(np.int64), 0, self.n_bins - 1)
        flat = bins + np.arange(self.n_cols) * self.n_bins          # column-major offsets
        self.hist += np.bincount(flat.ravel(), minlength=self.n_cols * self.n_bins).reshape(self.n_cols, self.n_bins)

    @property
    def mean(self) -> np.ndarray:
        return self.total / max(self.count, 1)

    def percentile(self, q: float) -> np.ndarray:
        cum = np.cumsum(self.hist, axis=1)
        target = q / 100 * self.count
        idx = (cum < target).sum(axis=1)
        return self.lo + np.minimum(idx, self.n_bins - 1) * self.step
