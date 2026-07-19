# S0-7 / OD-1 — OT Security Escalation Brief and Decision Record

**Prepared:** 2026-07-19 15:01 UTC
S0-7 acceptance status: **PENDING**
**Record state:** `pending`
**Structured record:** [`artifacts/phase0_ot_security/decision_record.json`](../artifacts/phase0_ot_security/decision_record.json)

> **This brief does not constitute OT approval.** It is an internal, sanitized meeting pack. It does not prove that an escalation was sent, a meeting was scheduled, a decision owner accepted responsibility, or a production path was approved.

## 1. Decision requested

OT Security is asked to approve or reject an achievable production data path from the plant historian/SCADA environment to the IT analytics host and to record:

1. the selected or rejected transport path;
2. source and destination systems;
3. the OT boundary or DMZ traversed;
4. allowed tags/data and export format;
5. timestamp semantics;
6. minimum, nominal, and maximum cadence;
7. nominal, P95, and worst-case sensor-to-analytics latency;
8. authentication, encryption, audit, and credential ownership;
9. reliability, retry, outage handling, and monitoring ownership;
10. a named OT decision owner and target decision date;
11. the horizons allowed to carry `served=true`; and
12. OT Security sign-off, conditions, or the reason for rejection.

The minimum S0-7 acceptance branch is either:

- a written production-path decision that records path, cadence, and latency; or
- if the decision is deferred, a written commitment from a **named OT decision owner** with a **target decision date** and an external evidence reference.

A generic role, internal draft, unsent invitation, hypothetical schedule, or undated “under review” note does not satisfy S0-7.

## 2. Current evidence state

- The current known path is an offline/manual SCADA export.
- Its production approval, configured cadence, and measured end-to-end latency are not recorded.
- No named OT decision owner, target date, meeting evidence, approval, or rejection is present in the repository.
- Therefore S0-7 remains `0/1`, Gate M0 remains open, and Phase 1 plus all model work remain NO-GO pending formal M0 closeout.

## 3. Non-negotiable security boundary

- Direction: **OT → DMZ → IT analytics host**.
- The transport must be one-way and read-only.
- No reverse path is permitted.
- No write method or write path to SCADA or PLC is permitted.
- Raw plant data must not be sent to public cloud services without written data-residency approval.
- Credentials, IP addresses, hostnames, firewall rules, sensitive topology, personal contact details, and raw plant data must not be committed to this repository.

Use an opaque ticket, controlled minutes, or controlled-document identifier as the external evidence reference.

## 4. RACI

| Role | Accountability |
|---|---|
| Product | Accountable for sending the escalation, preserving evidence, and requesting the decision |
| OT Security | Responsible for the decision and security conditions; holds veto authority |
| Data Engineering | Consulted for feasibility and for measuring achievable cadence and end-to-end latency |
| O&M, DevOps, Asset Owner | Consulted where plant operation, monitoring, hosting, or asset risk requires it |

The decision record must name the actual person who owns the OT decision. A role label alone is not the required named owner.

## 5. Paths to approve or reject

| Candidate | Required disposition | Questions that must be answered |
|---|---|---|
| Manual CSV | Approve for production, approve for offline use only, or reject | Who exports it, from where, to where, how often, how long until analytics can read it, and how failures are detected? |
| Read-only SFTP push through the OT DMZ | Approve with conditions or reject | Which OT-side process pushes, which DMZ/IT endpoint receives, what account owns the credential, what file/timestamp contract applies, and what retry/audit controls exist? |
| Read-only OPC-UA through an approved gateway | Approve with conditions or reject | Which gateway, allowed nodes/tags, read-only enforcement, sampling/publishing cadence, authentication/encryption, session retry, audit, and monitoring? |
| Other OT-approved one-way/read-only path | Define, approve with conditions, or reject | It must answer the same source, destination, boundary, data, cadence, latency, security, reliability, and ownership questions. |

For every candidate, record rejection reasons rather than silently omitting the option.

## 6. Cadence and latency measurement contract

Do not substitute an assumed SLA for evidence. Record separately:

- source emission or historian availability cadence;
- transfer/poll/push cadence;
- nominal and worst-case cadence;
- sensor event time and timestamp semantics;
- arrival time at the IT analytics host; and
- end-to-end latency from sensor event to analytics readability.

The following are candidate evaluation targets, not approved SLAs:

| Horizon scope | Candidate maximum end-to-end latency | Status |
|---|---:|---|
| 5 minutes | 60 seconds | Evaluation target only |
| 15 minutes | 3 minutes | Evaluation target only |
| At least 1 hour | 10 minutes | Evaluation target only |

The 10- and 30-minute horizons have no separate approved budget. OT Security, Product, and Data Engineering must explicitly assign or reject a budget; it must not be inferred from neighbouring horizons.

## 7. Servability decision

Until OD-1 evidence exists, every horizon remains provisional and no template value is evidence for `served=true`.

| Horizon (min) | Decision | Evidence/reference | Reason |
|---:|---|---|---|
| 5 | Pending | — | OD-1 pending |
| 10 | Pending | — | OD-1 pending; no explicit candidate budget |
| 15 | Pending | — | OD-1 pending |
| 30 | Pending | — | OD-1 pending; no explicit candidate budget |
| 60 | Pending | — | OD-1 pending |
| 120 | Pending | — | OD-1 pending |
| 180 | Pending | — | OD-1 pending |
| 360 | Pending | — | OD-1 pending |
| 1440 | Pending | — | OD-1 and operational NWP/egress conditions pending |
| 2880 | Pending | — | OD-1 and operational NWP/egress conditions pending |

If Manual CSV is selected permanently, all horizons below 6 hours must be `served=false`. Backtesting, QC, sensor-health analysis, intraday research, and day-ahead research may continue, subject to their own gates. Manual export does not support operational nowcasting.

## 8. Ready-to-send meeting request

**Subject:** Decision request OD-1 — read-only irradiance data path, cadence, latency, and servable horizons

**Body:**

> Product requests an OT Security decision for OD-1. We need an approved one-way/read-only path from OT through the approved boundary/DMZ to the IT analytics host, with no reverse or write path to SCADA/PLC. Please approve or reject Manual CSV, read-only SFTP push, read-only OPC-UA gateway, or another OT-approved one-way path. The written record must state allowed data, timestamp semantics, cadence, nominal/worst-case end-to-end latency, security controls, reliability/monitoring, and which horizons may be operationally served. If a final decision cannot be made at the meeting, please name the OT decision owner and commit a target decision date.

Attach or reference this brief through the organisation's controlled channel. Do not add credentials or sensitive topology.

## 9. Meeting agenda and minutes template

| Item | Written outcome |
|---|---|
| Approved/rejected path(s) | Pending |
| Source and destination | Pending |
| Direction and OT/DMZ boundary | Pending |
| Allowed tags/data | Pending |
| Format and timestamp semantics | Pending |
| Cadence min/nominal/max | Pending |
| Latency nominal/P95/worst-case | Pending |
| Authentication/encryption/audit/credential owner | Pending |
| Reliability/retry/outage handling/monitoring | Pending |
| Named OT decision owner | Pending |
| Target decision date | Pending |
| Horizon-by-horizon `served` outcome | Pending |
| OT sign-off, conditions, or rejection reason | Pending |
| External ticket/minutes/controlled-document reference | Pending |

## 10. Record-state rules

| State | Minimum evidence | Gate effect |
|---|---|---|
| `pending` | Internal template only | No S0-7 acceptance; no M0 closeout |
| `scheduled` | External evidence reference + named OT decision owner + written ISO target date | Satisfies the S0-7 “date for a decision” branch; still requires formal M0 closeout |
| `decided` | External evidence + selected/rejected path + cadence + latency + approver/sign-off + servability | Satisfies the written-decision branch; still requires formal M0 closeout |

When qualifying evidence arrives, update the structured record, attach only sanitized facts or controlled references, synchronize PRD/Master Context/Roadmap together, run the status-contract and full suite, and then perform a separate formal M0 closeout. Do not automatically start Phase 1.
