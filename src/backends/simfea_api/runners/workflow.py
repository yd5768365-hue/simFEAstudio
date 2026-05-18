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


def public_freecad_prepomax_workflow(solvers: list[SolverDefinition]) -> dict:
    return {
        "alias": FREECAD_PREPOMAX_WORKFLOW_ALIAS,
        "label": "FreeCAD -> PrePoMax",
        "kind": "workflow",
        "executable": "WorkflowRunner",
        "description": "Run the FreeCAD smoke geometry step, then run the configured PrePoMax regeneration step in one archive.",
        "artifact_patterns": workflow_artifact_patterns(solvers),
        "steps": [public_solver(solver) for solver in solvers],
    }
