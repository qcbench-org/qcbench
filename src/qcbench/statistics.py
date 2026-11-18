"""Shot-count validation, intervals and bounded exponential coherence fits."""
import math
from statistics import NormalDist
import warnings
import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit


def validate_counts(counts, n_qubits):
    if not isinstance(counts,dict) or not counts: raise ValueError("Counts must be a nonempty bitstring-to-integer object")
    for bits,count in counts.items():
        if not isinstance(bits,str) or len(bits)!=n_qubits or set(bits)-{"0","1"}:
            raise ValueError("Counts keys must be fixed-width binary strings (MSB left)")
        if type(count) is not int or count<0: raise ValueError("Counts must be nonnegative integers, not probabilities")
    if sum(counts.values())<=0: raise ValueError("Counts must contain at least one shot")
    return counts


def wilson(successes, shots, confidence=.95):
    if type(shots) is not int or type(successes) is not int or not 0<=successes<=shots or shots<=0:
        raise ValueError("Require integer 0 <= successes <= shots, shots > 0")
    if type(confidence) not in (int,float) or not 0<confidence<1: raise ValueError("confidence must be between zero and one")
    p=successes/shots; z=NormalDist().inv_cdf((1+confidence)/2); z2=z*z
    center=(p+z2/(2*shots))/(1+z2/shots)
    half=z*math.sqrt(p*(1-p)/shots+z2/(4*shots*shots))/(1+z2/shots)
    return dict(estimate=p,interval=[max(0.,center-half),min(1.,center+half)],confidence=confidence,
                successes=successes,shots=shots,method="Wilson score interval")


def marginal_successes(counts, logical_qubit, value):
    return sum(c for bits,c in counts.items() if int(bits[-1-logical_qubit])==value)


def fit_decay(points):
    """Fit p(t)=p_inf+(p_zero-p_inf)*exp(-t/T); return explicit non-fit states."""
    t=np.array([p["time_us"] for p in points],dtype=float)
    p=np.array([p["successes"]/p["shots"] for p in points])
    shots=np.array([p["shots"] for p in points],dtype=float)
    if len(set(t))<5 or max(t)<=0:
        return dict(status="unidentifiable",reason="Need five distinct effective delay times",points=points)
    if np.ptp(p)<max(.03,2/math.sqrt(float(min(shots)))):
        return dict(status="unidentifiable",reason="Insufficient measured decay contrast",points=points)
    scale=float(max(t)); x=t/scale
    def model(x,p_zero,p_inf,tau): return p_inf+(p_zero-p_inf)*np.exp(-x/tau)
    sigma=np.sqrt(np.maximum(p*(1-p),1/(4*shots))/shots)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",OptimizeWarning)
            params,cov=curve_fit(model,x,p,p0=[float(p[0]),float(p[-1]),.4],sigma=sigma,
                                 absolute_sigma=True,bounds=([0,0,1e-6],[1,1,1000]),maxfev=20000)
        p_zero,p_inf,tau=[float(v) for v in params]
        std=float(math.sqrt(max(0,cov[2,2]))*scale)
        if not np.isfinite(cov).all() or std>=tau*scale or p_zero-p_inf<.03 or tau>=999:
            return dict(status="unidentifiable",reason="Fit parameters are poorly constrained",points=points)
        chi2=float(sum(((p-model(x,*params))/sigma)**2))
        return dict(status="fitted",decay_time_us=tau*scale,decay_time_std_us=std,p_zero=p_zero,p_inf=p_inf,
                    chi_squared=chi2,degrees_of_freedom=len(points)-3,points=points,
                    reduced_chi_squared=chi2/(len(points)-3),
                    fit_quality="model_mismatch" if chi2/(len(points)-3)>5 else "inspect_residuals",
                    method="Bounded weighted nonlinear least squares; asymptotic covariance uncertainty")
    except (RuntimeError,ValueError,OptimizeWarning) as exc:
        return dict(status="unidentifiable",reason=str(exc),points=points)
