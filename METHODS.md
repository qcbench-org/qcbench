# Methods and scope

All probabilities are computed directly from integer counts. No readout mitigation, noise inversion or SPAM separation is performed. The generator and analysis implementations are original; the scientific observables and statistical estimators below are standard mathematical methods.

## Readout and mirror success

For a qubit prepared in b, the assignment-error estimate is the number of shots with measured value 1-b divided by shots. Preparation pulses and initialization errors can contribute to this statistic. A mirror circuit estimates the fraction returning all selected measured bits to zero. Its forward layers and inverse have explicit barriers. It is a circuit-level return probability, not randomized benchmarking, gate fidelity, quantum volume or a proof of quantum advantage.

For k successes in N independent shots, Wilson intervals use p=k/N and z equal to the standard normal quantile for the chosen two-sided confidence:

    center = (p + z²/(2N)) / (1 + z²/N)
    half = z sqrt(p(1-p)/N + z²/(4N²)) / (1 + z²/N)

Interval endpoints are center +/- half. This avoids a falsely zero-width uncertainty at observed p=0 or p=1. Coverage remains approximate, especially at extreme probabilities and low shots. Reference: E. B. Wilson, *Probable Inference, the Law of Succession, and Statistical Inference* (1927), [DOI](https://doi.org/10.1080/01621459.1927.10502953).

## GHZ fidelity

Target |GHZ+> = (|0...0> + |1...1>)/sqrt(2). For a stable state rho,

    F = (P(0...0) + P(1...1) + C) / 2
    C = (1/n) sum_{k=0}^{n-1} (-1)^k <M(k*pi/n) tensor ... tensor M(k*pi/n)>
    M(theta) = cos(theta) X + sin(theta) Y

Z-basis shots estimate the population term. Apply RZ(-theta) then H on each qubit before computational-basis measurement to obtain M(theta). Even parity corresponds to expectation +1. Defining p_k as the probability that parity equals k modulo 2 gives

    F_hat = population_hat/2 + (1/n) sum_k p_k_hat - 1/2.

A Z-only measurement cannot distinguish an ideal GHZ state from its incoherent 50:50 mixture. Both have population one, but fidelities one and one-half respectively. The test suite checks the full formula against independently calculated Born probabilities for arbitrary complex states on two, three and four qubits.

For a requested error probability alpha, each of the n+1 component Wilson intervals uses confidence 1-alpha/(n+1). Their weighted endpoints produce the reported combined interval, clipped to the physical fidelity range [0,1]. The point estimator is not clipped and can be negative due to finite shots or inconsistent measurements. Bonferroni does not make an approximate component interval exact; this result does not constitute device-independent certification. State drift and errors in the measurement rotations can bias it. The n+1-setting method is described by O. Gühne, C.-Y. Lu, W.-B. Gao and J.-W. Pan, *Toolbox for entanglement detection and fidelity estimation* ([arXiv:0706.2432](https://arxiv.org/abs/0706.2432)).

## Coherence experiments

T1: prepare |1>, idle for t, then measure probability one.

Echo: RY(pi/2), idle t/2, X, idle t/2, RY(pi/2), then measure probability one. The ideal zero-noise sequence returns |1>. Its decay constant is an echo coherence estimate, not Ramsey T2*.

For both experiments, fit

    p(t) = p_inf + (p_zero - p_inf) exp(-t/T),

with p_zero and p_inf bounded to [0,1] and positive T. Times are rescaled by the longest delay for numerical conditioning. Fit weights use a plug-in binomial variance with a finite floor to avoid singular weights at observed zero/one probabilities. Uncertainty is the local asymptotic covariance from weighted nonlinear least squares, not a bootstrap or a model-independent coverage guarantee. A free asymptote can be difficult to identify without a sufficiently long delay range.

At least five distinct effective times are needed. Very small contrast, covariance failure, a time error as large as the fitted time, negligible fitted decaying contrast or an upper-bound fit returns unidentifiable. Reduced chi-squared above five is flagged as model_mismatch; this threshold is a diagnostic heuristic, not a calibrated hypothesis test. Raw time points, shots and probabilities are preserved.

Effective times from the device adapter include rounded explicit idle delays and exclude pulse durations. Different providers may implement delays, echo pulses, resets, scheduling and dynamical decoupling differently. Compare experiments only after reviewing these settings and the compiled circuit. Calibration drift, heating, leakage and correlated shots are outside the single-exponential model and covariance uncertainty.

## Provenance

A deterministic plan fingerprint binds the generator version, parameters, physical mapping and all logical operations. Dataset labels are declared by the caller; they are not signatures or independent hardware attestations. Sampler collection assumes the original publication order and fixed `meas` register. Preserve raw counts, plan, job ID, compiled execution metadata and acquisition conditions when publishing measurements. Synthetic demonstrations must remain labelled synthetic.
