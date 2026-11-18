# Contributing

Contribute protocols, provider adapters and analysis improvements through issues and pull requests. Implementations must be independently authored or include required licenses and attribution. Preserve scholarly credit for measurement methods.

A protocol must state the physical experiment, state/gate conventions, timing units, output counts format, estimator, statistical assumptions and limits of interpretation. Include independent mathematical tests and validation of malformed inputs. Distinguish fitted parameters, circuit success and gate fidelity; do not invent aggregate hardware scores.

Adapters must preserve publication order, bit order, register mapping and effective timing metadata. Keep SDKs optional. No tests, CI or examples may submit cloud jobs by default. All live submission paths require an explicit opt-in; tests must use local backends or stubs. Never include account credentials, raw private device data or unsupported performance claims.

Changing existing circuits or estimators requires a suite or package version change. Do not silently reinterpret historical datasets. Keep synthetic data visibly labelled in all exports.
