import math
import logging
from datetime import datetime
from typing import List, Tuple

logger = logging.getLogger(__name__)

class AILEE_Monitor:
    """
    Monitors and calculates the Effective Optimization Gain (Δv) for an AI operation
    based on the AILEE equation.
    """

    def __init__(self, Isp: float, eta: float, alpha: float, v0: float):
        if not all(isinstance(arg, (int, float)) for arg in [Isp, eta, alpha, v0]):
            raise ValueError("All AILEE parameters (Isp, eta, alpha, v0) must be numeric.")
        if Isp <= 0 or eta <= 0:
            raise ValueError("Isp and eta must be positive.")
        
        self.Isp = float(Isp)
        self.eta = float(eta)
        self.alpha = float(alpha)
        self.v0 = float(v0)
        
        # Stores time-series data as (timestamp, P_input, w, v, M)
        self.time_series_data: List[Tuple[datetime, float, float, float, float]] = []

    def record_metrics(
        self,
        timestamp: datetime,
        P_input: float,
        w: float,
        v: float,
        M: float
    ):
        """Records a snapshot of the dynamic metrics at a specific timestamp."""
        if not isinstance(timestamp, datetime):
            raise TypeError("Timestamp must be a datetime object.")
        if not all(isinstance(arg, (int, float)) for arg in [P_input, w, v, M]):
            raise ValueError("P_input, w, v, M must be numeric.")
        if M <= 0:
            logger.warning(f"Model Inertia (M) is zero or negative ({M}). Using a small positive value to avoid errors.")
            M = 1e-9

        self.time_series_data.append((timestamp, float(P_input), float(w), float(v), float(M)))

    def calculate_delta_v(self) -> float:
        """
        Calculates the Effective Optimization Gain (Δv) by numerically integrating
        the AILEE equation over the recorded time series data.
        """
        if len(self.time_series_data) < 2:
            logger.warning("Insufficient data points to calculate Δv. Need at least 2.")
            return 0.0

        # **PERFORMANCE IMPROVEMENT**: Sort the data once here, just before calculation.
        self.time_series_data.sort(key=lambda x: x[0])

        integral_sum = 0.0
        
        for i in range(len(self.time_series_data) - 1):
            t1, P1, w1, v1, M1 = self.time_series_data[i]
            t2, P2, w2, v2, M2 = self.time_series_data[i+1]

            dt = (t2 - t1).total_seconds()
            if dt <= 0:
                continue

            # Average values for the interval (trapezoidal rule)
            P_avg = (P1 + P2) / 2.0
            w_avg = (w1 + w2) / 2.0
            v_avg = (v1 + v2) / 2.0
            M_avg = (M1 + M2) / 2.0

            if M_avg <= 0:
                logger.warning(f"Average Model Inertia (M_avg) is non-positive in interval. Skipping.")
                continue
            
            try:
                # Numerator: P_input * e^(-α*w^2) * e^(2α*v0) * v
                # Combine exponential terms for clarity and a minor optimization
                exponent = (2 * self.alpha * self.v0) - (self.alpha * (w_avg**2))
                numerator_term = P_avg * math.exp(exponent) * v_avg
                
                integral_sum += (numerator_term / M_avg) * dt
            except OverflowError:
                logger.error(f"Numerical overflow during integral calculation. Check input parameters.")
                return 0.0

        try:
            # Final Δv = Isp * η * e^(-α*v0^2) * integral_sum
            pre_factor = self.Isp * self.eta * math.exp(-self.alpha * (self.v0**2))
            delta_v = pre_factor * integral_sum
        except OverflowError:
            logger.error(f"Numerical overflow during final Δv calculation. Check input parameters.")
            return 0.0

        return delta_v

    def reset_data(self):
        """Clears all recorded time-series data."""
        self.time_series_data = []
        logger.debug("AILEE_Monitor data has been reset.")
