import math
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class AILEE_Monitor:
    """
    Monitors and calculates the Effective Optimization Gain (Δv) for an AI operation
    based on the AILEE equation, analogous to the rocket equation.

    Δv = Isp * η * e^(-α * v0^2) * ∫[0 to tf] (P_input(t) * e^(-α * w(t)^2) * e^(2α * v0) * v(t)) / M(t) dt

    This class can be extended to also incorporate the L (Love Resonance) equation components
    (C, I, Omega, Psi) for a composite resonance score, if desired.

    Parameters:
        Isp (float): Specific Efficiency - inherent model learning capability per resource.
        eta (float): System Efficiency Factor - how well input resources convert to gains.
        alpha (float): Resonance Sensitivity Coefficient - damping/amplification factor.
        v0 (float): Initial Velocity/Entropy - baseline state of the AI model.
    """
    def __init__(self, Isp: float, eta: float, alpha: float, v0: float):
        if not all(isinstance(arg, (int, float)) for arg in [Isp, eta, alpha, v0]):
            raise ValueError("All AILEE parameters (Isp, eta, alpha, v0) must be numeric.")
        if Isp <= 0 or eta <= 0:
            raise ValueError("Isp and eta must be positive values.")
        if alpha < 0:
            logger.warning("Alpha (Resonance Sensitivity Coefficient) is negative. This will lead to amplification rather than damping.")
        
        self.Isp = float(Isp)
        self.eta = float(eta)
        self.alpha = float(alpha)
        self.v0 = float(v0)
        
        # Stores time-series data as (timestamp, P_input, w, v, M)
        self.time_series_data: List[Tuple[datetime, float, float, float, float]] = []

    def record_metrics(self,
                       timestamp: datetime,
                       P_input: float,
                       w: float,
                       v: float,
                       M: float):
        """
        Records a snapshot of the dynamic metrics at a specific timestamp.

        Args:
            timestamp (datetime): The time at which these metrics were recorded.
            P_input (float): Input Power Over Time (e.g., compute power, data throughput).
            w (float): Workload Intensity Over Time (e.g., task complexity).
            v (float): Velocity or Learning Rate Over Time (e.g., model parameter evolution rate).
            M (float): Model Inertia (e.g., model size, computational cost).
        """
        if not isinstance(timestamp, datetime):
            raise TypeError("Timestamp must be a datetime object.")
        if not all(isinstance(arg, (int, float)) for arg in [P_input, w, v, M]):
            raise ValueError("P_input, w, v, M must be numeric.")
        if P_input < 0 or w < 0 or v < 0:
             logger.warning(f"Negative value detected for P_input ({P_input}), w ({w}), or v ({v}). These should typically be non-negative.")
        if M <= 0: # M should be positive to avoid division by zero or negative inertia
            logger.warning(f"Model Inertia (M) is zero or negative ({M}) at {timestamp}. Setting to a very small positive value to avoid division by zero.")
            M = 1e-9 # A very small positive number

        self.time_series_data.append((timestamp, float(P_input), float(w), float(v), float(M)))
        # Keep data sorted by timestamp for correct integration (though append usually keeps order)
        self.time_series_data.sort(key=lambda x: x[0])

    def calculate_delta_v(self) -> float:
        """
        Calculates the Effective Optimization Gain (Δv) by numerically integrating
        the AILEE equation over the recorded time series data.

        Returns:
            float: The calculated Δv (resonance_score). Returns 0.0 if insufficient data.
        """
        if len(self.time_series_data) < 2:
            logger.warning("Insufficient data points to calculate Δv. Need at least 2 points.")
            return 0.0

        integral_sum = 0.0
        
        # Iterate through the sorted time series data to perform numerical integration
        # Using the trapezoidal rule for approximation
        for i in range(len(self.time_series_data) - 1):
            t1, P1, w1, v1, M1 = self.time_series_data[i]
            t2, P2, w2, v2, M2 = self.time_series_data[i+1]

            # Calculate time difference in seconds
            dt = (t2 - t1).total_seconds()
            if dt <= 0: # Skip if timestamps are identical or out of order (should be sorted)
                logger.debug(f"Skipping interval due to non-positive dt: {dt} between {t1} and {t2}")
                continue

            # Average values for the current interval
            P_avg = (P1 + P2) / 2.0
            w_avg = (w1 + w2) / 2.0
            v_avg = (v1 + v2) / 2.0
            M_avg = (M1 + M2) / 2.0

            # Ensure M_avg is not zero for the denominator
            if M_avg <= 0:
                logger.warning(f"Average Model Inertia (M_avg) is zero or negative ({M_avg}) in interval {t1}-{t2}. Skipping this interval.")
                continue
            
            # Calculate the integrand for the current interval
            # Numerator: P_input(t) * e^(-α * w(t)^2) * e^(2α * v0) * v(t)
            try:
                numerator_term = P_avg * math.exp(-self.alpha * (w_avg**2)) * math.exp(2 * self.alpha * self.v0) * v_avg
            except OverflowError:
                logger.error(f"OverflowError during numerator calculation in interval {t1}-{t2}. Check alpha, w_avg, v0 values.")
                return 0.0 # Return 0 or handle error appropriately

            # Add to integral sum (integrand / M(t)) * dt
            integral_sum += (numerator_term / M_avg) * dt

        # Calculate the final Δv using the full AILEE equation
        try:
            delta_v = self.Isp * self.eta * math.exp(-self.alpha * (self.v0**2)) * integral_sum
        except OverflowError:
            logger.error(f"OverflowError during final delta_v calculation. Check Isp, eta, alpha, v0, integral_sum values.")
            return 0.0

        return delta_v

    def reset_data(self):
        """Clears all recorded time-series data."""
        self.time_series_data = []


