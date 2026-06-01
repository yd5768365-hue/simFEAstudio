from ..config import SolverDefinition
from .solver import public_solver

FREECAD_PREPOMAX_WORKFLOW_ALIAS = "freecad-prepomax"
FREECAD_PREPOMAX_STEP_ALIASES = ("freecad", "prepomax-regenerate")


def workflow_artifact_patterns(solvers: list[SolverDefinition]) -> list[str]:
    patterns: list[str] = []
    for solver in solvers:
        for pattern in solver.artifact_patterns:
            if pattern not in patterns:
                patterns.append(pattern)
    if "result.txt" not in patterns:
        patterns.append("result.txt")
    return patterns


def public_workflow(alias: str, label: str, solvers: list[SolverDefinition]) -> dict:
    return {
        "alias": alias,
        "label": label,
        "kind": "workflow",
        "executable": "WorkflowRunner",
        "description": f"Custom workflow with {len(solvers)} steps: {' -> '.join(s.label for s in solvers)}",
        "artifact_patterns": workflow_artifact_patterns(solvers),
        "steps": [public_solver(solver) for solver in solvers],
    }


def public_freecad_prepomax_workflow(solvers: list[SolverDefinition]) -> dict:
    return public_workflow(FREECAD_PREPOMAX_WORKFLOW_ALIAS, "FreeCAD -> PrePoMax", solvers)
