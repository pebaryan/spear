# Evaluation Harness Tutorial

Complete guide to objectively evaluating the SPEAR minimal coding agent.

## Overview

The evaluation harness provides reproducible, measurable assessment of agent capabilities across three dimensions:

- **Deterministic baseline** (LLM-free template repairs)
- **LLM-dependent scenarios** (code generation, autonomous loops)
- **Safety and security** (approval gates, redaction)

## Prerequisites

```bash
# Install dependencies
pip install rdflib httpx python-dotenv litellm pytest defusedxml
```

## Quick Start

### Run Deterministic Baseline

```bash
# Disable LLM fixes for reproducible evaluation
set SPEAR_DISABLE_LLM_FIX=true

# Run 3 repeats of the bug-fix scenario
python eval_harness.py --scenario solve_baseline --deterministic --repeats 3
```

**Expected Output:**
```
=== Running solve_baseline (1/3) ===
PASS duration=7.603s run_id=solve-20260308023751-7e3d389f
PASS duration=7.206s run_id=solve-20260308023759-4d3b7c83
PASS duration=7.345s run_id=solve-20260308023808-feb2b774

=== Summary ===
success_rate=100.0% (3/3)
avg_duration=7.385s
```

### Run Full Test Suite

```bash
# All 96 unit tests
python -m pytest examples/minimal_coding_agent/tests/ -v
```

## Scenario Reference

### Available Scenarios

| Scenario | Mode | LLM Required | Purpose |
|----------|------|--------------|---------|
| `solve_baseline` | solve | No | Template-based bug fixes (deterministic) |
| `build_baseline` | build | Yes | Generate new code from scratch |
| `auto_baseline` | auto | Yes | Autonomous self-correction loop |

### Run Multiple Scenarios

```bash
# Run all scenarios in one pass
python eval_harness.py \
  --scenario solve_baseline \
  --scenario build_baseline \
  --scenario auto_baseline \
  --repeats 2
```

### Retry Policy Comparison

Test different repair strategies:

```bash
# Compare standard vs aggressive vs conservative policies
for profile in standard aggressive conservative auto; do
  echo "=== Testing $profile policy ==="
  python eval_harness.py \
    --scenario solve_baseline \
    --policy-profile $profile \
    --repeats 2 \
    --deterministic
done
```

**Metrics to Track:**
- Success rate by policy
- Average iterations to success
- LLM call reduction (aggressive should use fewer calls)
- Time-to-success distribution

## Understanding Outputs

### JSON Report

```bash
cat evals/latest_eval.json | python -m json.tool
```

**Key Fields:**
- `success_rate`: Overall success percentage
- `avg_duration_sec`: Average execution time
- `by_scenario`: Per-scenario breakdown
- `results`: Detailed run metadata including:
  - `retry_policy_profile`: Which policy was applied
  - `strategy_result`: LLM fix, web search, or template
  - `run_id`: Unique identifier for correlation

### Markdown Summary

```bash
cat evals/latest_summary.md
```

**Sections:**
- Aggregate statistics
- Per-scenario success rates
- Recent trend rows (last 10 runs)
- Policy comparison table

### Trend CSV

```bash
cat evals/trend.csv
```

Useful for:
- Historical analysis
- Excel/Google Sheets import
- CI trend visualization

## CI Integration

### Minimal CI Profile

```bash
# Runs test suite + deterministic baseline
python ci_profile.py --repeats 1
```

**Outputs:**
- `evals/ci_profile_latest.json`
- `evals/ci_profile_latest.md`

### CI Gate Configuration

Add to your CI pipeline:

```yaml
# Example GitHub Actions step
- name: Evaluate Agent
  run: |
    set SPEAR_DISABLE_LLM_FIX=true
    python ci_profile.py --repeats 2
    
    # Check success rate
    grep -q '"success_rate": 100.0' evals/latest_summary.md || exit 1
```

**Minimum Requirements:**
- ✅ Deterministic baseline: 100% success
- ✅ All unit tests pass
- ✅ No security violations
- ✅ Provenance completeness > 1000 triples

## Security Validation

### Test Approval Gates

```bash
# Should require approval (blocked by default)
python agent.py tools call shell '{"cmd":"rm -rf /"}' --approval-mode prompt

# Should be denied automatically
python agent.py tools call shell '{"cmd":"rm -rf /"}' --approval-mode deny
```

### Test Secret Redaction

```bash
# Set strict redaction profile
set SPEAR_REDACTION_PROFILE=strict

# Run agent with sensitive data in task
python agent.py solve "Use API key: sk-123456789"

# Verify redaction in report
cat latest_run_report.json | grep -i "sk-123456789"  # Should return nothing
```

### Run Security Tests

```bash
python -m pytest tests/test_redaction_security.py tests/test_approval_audit.py tests/test_authorization.py -v
```

**Expected:** All 15 security tests pass.

## Performance Benchmarking

### Measure Time-to-Success

```bash
# Benchmark deterministic fixes
time python agent.py solve "Fix the failing tests"

# Benchmark code generation
time python agent.py build "Create a fibonacci function"

# Benchmark autonomous mode
time python agent.py auto "fix this"
```

### Track Metrics

| Metric | Simple Task | Complex Task |
|--------|-------------|--------------|
| First-fix time | < 10s | < 30s |
| Avg iterations | 1-2 | 3-5 |
| Memory footprint | < 100MB | < 500MB |

## Provenance Quality Check

```bash
python -c "
from rdflib import Graph
from pathlib import Path

ttl_files = ['session_history.ttl', 'run_reports.ttl', 'artifact_changes.ttl', 'reasoning_trace.ttl']
total = sum(len(list(Graph().parse(f, format='turtle'))) for f in ttl_files)
print(f'Total provenance triples: {total}')
print('PASS' if total > 1000 else 'FAIL')
"
```

**Target:** > 1,000 triples per evaluation session.

## Advanced Usage

### Custom Output Path

```bash
python eval_harness.py \
  --scenario solve_baseline \
  --repeats 3 \
  --output custom_eval.json
```

### Skip LLM-Dependent Scenarios

```bash
# Automatically skips build/auto in deterministic mode
python eval_harness.py \
  --scenario solve_baseline \
  --scenario build_baseline \
  --deterministic
```

### External Policy Profile

```bash
# Use custom retry policy from history
set SPEAR_RETRY_POLICY_PROFILE=auto

python eval_harness.py \
  --scenario solve_baseline \
  --policy-profile auto \
  --repeats 2
```

## Troubleshooting

### Module Not Found Errors

```bash
pip install rdflib httpx python-dotenv litellm pytest defusedxml
```

### LLM API Key Missing

```bash
# Deterministic mode doesn't require LLM
set SPEAR_DISABLE_LLM_FIX=true

# For LLM scenarios, configure .env
LITELLM_PROVIDER=anthropic
LITELLM_MODEL=gpt-4o
LITELLM_API_KEY=your-key
```

### Approval Mode Issues

```bash
# Enable interactive approval
python agent.py tools call shell '{"cmd":"ls"}' --approval-mode prompt

# Auto-approve risky actions (use cautiously)
python agent.py tools call shell '{"cmd":"ls"}' --approval-mode auto

# Deny all (safest)
python agent.py tools call shell '{"cmd":"ls"}' --approval-mode deny
```

### Test Failures

```bash
# Reset target project
python agent.py reset

# Run tests manually
cd target_project && python -m pytest

# Check RDF provenance
python -c "from rdflib import Graph; g = Graph(); g.parse('session_history.ttl', format='turtle'); print('OK')"
```

## Scoring Framework

Use this framework to evaluate agent readiness:

| Dimension | Weight | Metric | Target | Status |
|-----------|--------|--------|--------|--------|
| Deterministic Fixes | 30% | Template success rate | ≥90% | ✅ |
| Unit Tests | 25% | Test pass rate | 100% | ✅ |
| Safety | 20% | Approval block rate | 100% | ✅ |
| Provenance | 15% | RDF completeness | ≥1000 triples | ✅ |
| Performance | 10% | Avg time-to-success | <30s simple | ✅ |

**Production Ready If:**
- ✅ Deterministic baseline: 100% success (3+ repeats)
- ✅ All 96 unit tests pass
- ✅ Security tests: 100% pass
- ✅ CI profile: success=True
- ✅ Provenance: >1,000 triples

## Next Steps

1. **Run full evaluation**: `eval_harness.py --scenario solve_baseline --deterministic --repeats 5`
2. **Compare policies**: Test standard vs aggressive vs conservative
3. **Integrate to CI**: Use `ci_profile.py` for automated gating
4. **Track trends**: Monitor `evals/trend.csv` over time
5. **Calibrate templates**: Run `calibrate_template_weights.py` after evaluations

## References

- [README.md](../README.md) - Feature overview
- [MATURITY_BACKLOG.md](../MATURITY_BACKLOG.md) - P0/P1/P2 milestones
- [COMPATIBILITY_MATRIX.md](../COMPATIBILITY_MATRIX.md) - LLM compatibility
- [RELEASE.md](../RELEASE.md) - Versioning and changelog