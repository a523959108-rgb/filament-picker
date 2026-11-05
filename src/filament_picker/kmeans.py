from __future__ import annotations

import numpy as np

from .config import KMEANS_MAX_ITER, KMEANS_TOL


def sample_pixels(X: np.ndarray, max_n: int, seed: int = 0) -> np.ndarray:
    if len(X) <= max_n:
        return X
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(X), max_n, replace=False)
    return X[indices]


def kmeans(
    X: np.ndarray,
    k: int,
    seed: int = 0,
    max_iter: int = KMEANS_MAX_ITER,
    tol: float = KMEANS_TOL,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(X) == 0 or k < 1:
        raise ValueError("X must be non-empty and k must be at least 1")

    values = np.asarray(X, dtype=np.float64)
    k = min(k, np.unique(values, axis=0).shape[0])
    rng = np.random.default_rng(seed)
    centers = values[[rng.integers(len(values))]]

    while len(centers) < k:
        distances = values[:, np.newaxis, :] - centers[np.newaxis, :, :]
        d2 = np.sum(distances * distances, axis=2).min(axis=1)
        centers = np.vstack((centers, values[[rng.choice(len(values), p=d2 / d2.sum())]]))

    for _ in range(max_iter):
        distances = values[:, np.newaxis, :] - centers[np.newaxis, :, :]
        labels = np.argmin(np.sum(distances * distances, axis=2), axis=1)
        new_centers = centers.copy()
        for index in range(k):
            members = values[labels == index]
            if len(members) > 0:
                new_centers[index] = members.mean(axis=0)
        shift = np.max(np.abs(new_centers - centers))
        centers = new_centers
        if shift < tol:
            break

    distances = values[:, np.newaxis, :] - centers[np.newaxis, :, :]
    labels = np.argmin(np.sum(distances * distances, axis=2), axis=1).astype(np.int64)
    shares = np.bincount(labels, minlength=k).astype(np.float64) / len(values)
    return centers, labels, shares
