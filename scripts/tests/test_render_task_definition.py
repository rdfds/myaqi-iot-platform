from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.deploy.render_task_definition import render_task_definition  # noqa: E402


def test_render_task_definition_replaces_only_release_fields() -> None:
    source = {
        "taskDefinition": {
            "taskDefinitionArn": "arn:old",
            "revision": 4,
            "status": "ACTIVE",
            "family": "myaqi-staging-api",
            "networkMode": "awsvpc",
            "requiresAttributes": [{"name": "ecs.capability.logging-driver.awslogs"}],
            "containerDefinitions": [
                {
                    "name": "api",
                    "image": "repository:old",
                    "environment": [
                        {"name": "APP_ENVIRONMENT", "value": "staging"},
                        {"name": "APP_REVISION", "value": "old"},
                    ],
                }
            ],
        }
    }

    rendered = render_task_definition(
        source,
        container_name="api",
        image="repository:abc123",
        revision="abc123",
    )

    assert "taskDefinitionArn" not in rendered
    assert "revision" not in rendered
    assert "requiresAttributes" not in rendered
    container = rendered["containerDefinitions"][0]
    assert container["image"] == "repository:abc123"
    assert container["environment"] == [
        {"name": "APP_ENVIRONMENT", "value": "staging"},
        {"name": "APP_REVISION", "value": "abc123"},
    ]
    assert container["dockerLabels"] == {
        "org.opencontainers.image.revision": "abc123"
    }


def test_render_task_definition_rejects_wrong_container() -> None:
    source = {"containerDefinitions": [{"name": "worker", "image": "old"}]}

    try:
        render_task_definition(
            source,
            container_name="api",
            image="new",
            revision="abc123",
        )
    except ValueError as error:
        assert "exactly one container named api" in str(error)
    else:
        raise AssertionError("Expected missing container to fail")
