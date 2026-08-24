from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

READ_ONLY_TASK_FIELDS = {
    "compatibilities",
    "deregisteredAt",
    "registeredAt",
    "registeredBy",
    "requiresAttributes",
    "revision",
    "status",
    "taskDefinitionArn",
}


def render_task_definition(
    document: dict[str, object],
    *,
    container_name: str,
    image: str,
    revision: str,
) -> dict[str, object]:
    source = document.get("taskDefinition", document)
    if not isinstance(source, dict):
        raise ValueError("Expected a taskDefinition object")
    rendered = copy.deepcopy(source)
    for field in READ_ONLY_TASK_FIELDS:
        rendered.pop(field, None)

    definitions = rendered.get("containerDefinitions")
    if not isinstance(definitions, list):
        raise ValueError("Task definition has no containerDefinitions list")
    matches = [
        container
        for container in definitions
        if isinstance(container, dict) and container.get("name") == container_name
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one container named {container_name}")
    container = matches[0]
    container["image"] = image
    environment = container.setdefault("environment", [])
    if not isinstance(environment, list):
        raise ValueError("Container environment must be a list")
    environment[:] = [
        value
        for value in environment
        if not isinstance(value, dict) or value.get("name") != "APP_REVISION"
    ]
    environment.append({"name": "APP_REVISION", "value": revision})
    labels = container.setdefault("dockerLabels", {})
    if not isinstance(labels, dict):
        raise ValueError("Container dockerLabels must be an object")
    labels["org.opencontainers.image.revision"] = revision
    return rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render an immutable ECS task revision")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--revision", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    rendered = render_task_definition(
        document,
        container_name=args.container,
        image=args.image,
        revision=args.revision,
    )
    args.output.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
