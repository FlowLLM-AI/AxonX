"""Validate and index plugin contributions across persisted records."""

from ....schema import JobConfig


def index_records(
    records: dict[str, dict],
) -> tuple[dict[str, JobConfig], dict[str, dict[str, str]], dict[tuple[str, str], str]]:
    """Validate uniqueness and return jobs, components, and owners."""
    jobs: dict[str, JobConfig] = {}
    components: dict[str, dict[str, str]] = {}
    component_owners: dict[tuple[str, str], str] = {}
    task_owners: dict[str, str] = {}
    job_owners: dict[str, str] = {}

    for owner, record in records.items():
        for name in record.get("tasks", {}):
            if name in task_owners:
                previous = task_owners[name]
                raise ValueError(f"Task {name!r} is provided by plugins {previous!r} and {owner!r}")
            task_owners[name] = owner
        for name, raw_config in record.get("jobs", {}).items():
            if name in job_owners:
                previous = job_owners[name]
                raise ValueError(f"Job {name!r} is provided by plugins {previous!r} and {owner!r}")
            jobs[name] = JobConfig.model_validate(raw_config)
            job_owners[name] = owner
        for component_type, backends in record.get("components", {}).items():
            registered = components.setdefault(component_type, {})
            for backend, target in backends.items():
                identity = (component_type, backend)
                if identity in component_owners:
                    previous = component_owners[identity]
                    raise ValueError(
                        f"Component backend {component_type}:{backend} is provided by "
                        f"plugins {previous!r} and {owner!r}",
                    )
                registered[backend] = target
                component_owners[identity] = owner
    return jobs, components, component_owners
