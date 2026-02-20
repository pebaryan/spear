import subprocess
import sys
import time
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, XSD

ROOT = Path(__file__).parent
TARGET = ROOT / "target_app"
APP_FILE = TARGET / "app.py"
POLICY = {
    "blocked_commands": ["curl", "wget", "rm", "pip install"],
    "allowed_paths": [str(TARGET.resolve())],
}

AG = Namespace("http://example.org/agent#")
PROV = Namespace("http://www.w3.org/ns/prov#")


def now_literal():
    return Literal(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), datatype=XSD.dateTime
    )


def log_action(g, run, label, tool, target=None, status=None, reason=None):
    action = URIRef(f"{run}/action/{len(list(g.subjects(RDF.type, AG.Action)))}")
    g.add((action, RDF.type, AG.Action))
    g.add((action, RDFS.label, Literal(label)))
    g.add((action, AG.tool, Literal(tool)))
    if status:
        g.add((action, AG.status, Literal(status)))
    g.add((action, PROV.wasAssociatedWith, run))
    g.add((action, PROV.startedAtTime, now_literal()))
    if target:
        g.add((action, PROV.used, target))
    if reason:
        g.add((action, AG.reason, Literal(reason)))
    return action


def apply_fix():
    text = APP_FILE.read_text()
    text = text.replace("return total / (count + 1)", "return total / count")
    # Adjust test expectation: zero count should raise ValueError, not ZeroDivisionError
    tests = (TARGET / "tests.py").read_text()
    tests = tests.replace(
        "with pytest.raises(ZeroDivisionError):", "with pytest.raises(ValueError):"
    )
    APP_FILE.write_text(text)
    (TARGET / "tests.py").write_text(tests)


def run_pytest():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests.py"],
        cwd=TARGET,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def blocked(cmd: str):
    return any(cmd.strip().startswith(b) for b in POLICY["blocked_commands"])


def main():
    g = Graph()
    g.bind("ag", AG)
    g.bind("prov", PROV)

    run = URIRef("http://example.org/run/1")
    g.add((run, RDF.type, AG.Run))
    g.add((run, RDFS.label, Literal("Demo agent run")))

    # Step 1: initial test (expected to fail)
    action_test0 = log_action(g, run, "run pytest (baseline)", "pytest")
    code, out = run_pytest()
    g.add((action_test0, AG.status, Literal("failed" if code else "passed")))
    g.add((action_test0, AG.output, Literal(out)))

    # Step 2: attempt blocked command
    cmd = "curl http://example.com"
    if blocked(cmd):
        log_action(
            g,
            run,
            "blocked shell command",
            "shell",
            status="blocked",
            reason="policy: no network commands",
        )
    else:
        subprocess.run(cmd, shell=True, check=False)

    # Step 3: apply fix
    target_file = URIRef(APP_FILE.resolve().as_uri())
    action_fix = log_action(
        g, run, "fix running_average bug", "edit", target=target_file
    )
    apply_fix()
    g.add((action_fix, AG.status, Literal("completed")))

    # Step 4: re-run tests
    action_test1 = log_action(g, run, "run pytest (post-fix)", "pytest")
    code, out = run_pytest()
    g.add((action_test1, AG.status, Literal("passed" if code == 0 else "failed")))
    g.add((action_test1, AG.output, Literal(out)))

    ttl_path = ROOT / "demo-prov.ttl"
    g.serialize(destination=ttl_path, format="turtle")
    print(f"Provenance saved to {ttl_path}")
    print("Test output:\n" + out)
    if code != 0:
        sys.exit(code)


if __name__ == "__main__":
    main()
