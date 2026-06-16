"""Docker container operations for local admin control panel."""

from __future__ import annotations

from dataclasses import dataclass

import docker
from docker.errors import DockerException, NotFound

from app.config import settings


@dataclass
class ContainerInfo:
    id: str
    name: str
    service: str | None
    image: str
    state: str
    status: str
    health: str | None


def _client() -> docker.DockerClient:
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


def _project_label() -> str:
    return f"com.docker.compose.project={settings.docker_compose_project}"


def list_project_containers() -> list[ContainerInfo]:
    client = _client()
    try:
        containers = client.containers.list(all=True, filters={"label": _project_label()})
        out: list[ContainerInfo] = []
        for c in containers:
            attrs = c.attrs
            labels = attrs.get("Config", {}).get("Labels", {}) or {}
            state = attrs.get("State", {}) or {}
            health = (state.get("Health") or {}).get("Status")
            out.append(
                ContainerInfo(
                    id=c.id,
                    name=c.name,
                    service=labels.get("com.docker.compose.service"),
                    image=attrs.get("Config", {}).get("Image", c.image.tags[0] if c.image.tags else ""),
                    state=state.get("Status", c.status),
                    status=attrs.get("State", {}).get("Status", c.status),
                    health=health,
                )
            )
        out.sort(key=lambda x: (x.service or "", x.name))
        return out
    finally:
        client.close()


def _get_project_container(client: docker.DockerClient, name: str):
    try:
        c = client.containers.get(name)
    except NotFound as exc:
        raise KeyError("Container not found") from exc
    labels = c.attrs.get("Config", {}).get("Labels", {}) or {}
    if labels.get("com.docker.compose.project") != settings.docker_compose_project:
        raise KeyError("Container not found in this project")
    return c


def start_project_container(name: str) -> ContainerInfo:
    client = _client()
    try:
        c = _get_project_container(client, name)
        c.start()
        c.reload()
        attrs = c.attrs
        labels = attrs.get("Config", {}).get("Labels", {}) or {}
        state = attrs.get("State", {}) or {}
        health = (state.get("Health") or {}).get("Status")
        return ContainerInfo(
            id=c.id,
            name=c.name,
            service=labels.get("com.docker.compose.service"),
            image=attrs.get("Config", {}).get("Image", c.image.tags[0] if c.image.tags else ""),
            state=state.get("Status", c.status),
            status=attrs.get("State", {}).get("Status", c.status),
            health=health,
        )
    finally:
        client.close()


def get_project_container_logs(name: str, tail: int = 400) -> str:
    client = _client()
    try:
        c = _get_project_container(client, name)
        logs = c.logs(stdout=True, stderr=True, tail=max(1, min(tail, 5000)))
        return logs.decode("utf-8", errors="replace")
    finally:
        client.close()


def docker_available() -> tuple[bool, str | None]:
    client = _client()
    try:
        client.ping()
        return True, None
    except DockerException as exc:
        return False, str(exc)
    finally:
        client.close()
