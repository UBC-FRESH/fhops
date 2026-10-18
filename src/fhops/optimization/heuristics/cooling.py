"""Adaptive temperature schedules for simulated annealing.

FHOPS's default SA cooling is geometric (``temperature *= cooling_rate``); a geometric schedule
needs its constants tuned by trial for each scenario. This module adds the adaptive, polynomial-time
schedule of Aarts and Van Laarhoven (1985): the initial temperature is set from the average uphill
move, and the temperature is then decremented from the spread of the objective values seen at the
current temperature, so the schedule tunes itself to the instance.

The rule is stated for a minimisation objective. FHOPS maximises its score, so callers pass the
uphill magnitude as ``current_score - move_score`` (positive when the move makes things worse).

References
----------
Aarts, E. H. L., and Van Laarhoven, P. J. M. (1985). Statistical cooling: a general approach to
combinatorial optimization problems. *Philips Journal of Research*, 40(4), 193-226.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AdaptiveCooling:
    """The Aarts and Van Laarhoven (1985) polynomial-time cooling rule.

    Parameters
    ----------
    initial_acceptance : float, optional
        The acceptance ratio the initial temperature targets, in ``(0, 1)``. A move that raises
        the (maximised) score by the observed average uphill magnitude is accepted with this
        probability at ``c_0``. Defaults to 0.9.
    delta : float, optional
        The distance from stationarity the decrement allows; it must be positive. Defaults to 0.1.

    Raises
    ------
    ValueError
        If ``initial_acceptance`` is outside ``(0, 1)`` or ``delta`` is not positive.
    """

    initial_acceptance: float = 0.9
    delta: float = 0.1

    def __post_init__(self) -> None:
        """Reject parameters the cooling rule is undefined for."""
        if not 0.0 < self.initial_acceptance < 1.0:
            raise ValueError("initial_acceptance must be in (0, 1)")
        if self.delta <= 0.0:
            raise ValueError("delta must be positive")

    def initial_temperature(self, increases: Sequence[float]) -> float:
        """Return the initial temperature for a sample of uphill move magnitudes.

        ``c_0 = mean(positive dE) / ln(1 / chi_0)``, so a move that makes the score worse by the
        observed average is accepted with probability ``chi_0`` at ``c_0``.

        Parameters
        ----------
        increases : sequence of float
            The uphill magnitudes (``current_score - move_score``) of the sampled moves. Only
            positive values are used.

        Returns
        -------
        float
            The initial temperature, or ``0.0`` when no sampled move was uphill.
        """
        uphill = [change for change in increases if change > 0.0]
        if not uphill:
            return 0.0
        return (sum(uphill) / len(uphill)) / math.log(1.0 / self.initial_acceptance)

    def cool(self, temperature: float, spread: float) -> float:
        """Return the next temperature from the current one and its objective spread.

        ``c_{k+1} = c_k / (1 + c_k ln(1 + delta) / (3 sigma_k))``. A non-positive spread leaves the
        temperature unchanged, because the rule is undefined there.

        Parameters
        ----------
        temperature : float
            The current temperature.
        spread : float
            The population standard deviation of the scores at the current temperature.

        Returns
        -------
        float
            The next temperature.
        """
        if spread <= 0.0:
            return temperature
        return temperature / (1.0 + temperature * math.log1p(self.delta) / (3.0 * spread))


@dataclass
class AdaptiveSchedule:
    """Track the SA temperature with the Aarts and Van Laarhoven adaptive rule.

    The first ``window`` observations form a warm-up during which the temperature is ``inf`` (every
    move is accepted) and the uphill magnitudes are collected; the initial temperature is then set
    from their mean. Each following group of ``window`` observations recomputes the temperature from
    the population standard deviation of the scores seen.

    Parameters
    ----------
    window : int
        The number of observations per temperature. Must be positive.
    rule : AdaptiveCooling, optional
        The adaptive rule's parameters. Defaults to :class:`AdaptiveCooling` defaults.

    Attributes
    ----------
    temperature : float
        The temperature the next iteration should read (``inf`` during the warm-up).

    Raises
    ------
    ValueError
        If ``window`` is not positive.
    """

    window: int
    rule: AdaptiveCooling = field(default_factory=AdaptiveCooling)
    temperature: float = field(init=False, default=math.inf)
    _increases: list[float] = field(init=False, default_factory=list)
    _samples: list[float] = field(init=False, default_factory=list)
    _warmed: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Validate the window."""
        if self.window < 1:
            raise ValueError("window must be positive")

    def reset(self) -> None:
        """Re-arm the warm-up (used after an SA restart)."""
        self.temperature = math.inf
        self._increases.clear()
        self._samples.clear()
        self._warmed = False

    def observe(self, increase: float, score: float) -> None:
        """Record one observation, then advance the temperature.

        Parameters
        ----------
        increase : float
            The uphill magnitude the move proposed (``current_score - move_score``; positive when
            the move makes the score worse).
        score : float
            The maximised score of the current configuration after the move.
        """
        if not self._warmed:
            self._increases.append(increase)
            if len(self._increases) >= self.window:
                self.temperature = self.rule.initial_temperature(self._increases)
                self._increases.clear()
                self._warmed = True
            return
        self._samples.append(score)
        if len(self._samples) >= self.window:
            self.temperature = self.rule.cool(self.temperature, statistics.pstdev(self._samples))
            self._samples.clear()

    @staticmethod
    def effective_window(iterations: int, window: int | None) -> int:
        """Return the warm-up window for an iteration budget.

        The warm-up needs a whole window of iterations, so the window is capped at half the budget
        (and at ``64`` when ``window`` is ``None``).

        Parameters
        ----------
        iterations : int
            The iteration budget.
        window : int or None
            The requested window, or ``None`` to auto-scale (``64`` capped at half the budget).

        Returns
        -------
        int
            The window to use, at least one.
        """
        requested = 64 if window is None else window
        return max(1, min(requested, max(1, iterations // 2)))
