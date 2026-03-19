"""Contract-first work-item models kept only as backup."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkItemStatus(StrEnum):
    RECEIVED = "received"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkItemSource(BaseModel):
    channel: str
    system: str = ""
    event_type: str = ""
    external_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("channel", mode="before")
    @classmethod
    def _normalize_channel(cls, value: Any) -> str:
        channel = str(value).strip()
        if not channel:
            raise ValueError("work item source channel must not be empty")
        return channel


class WorkItemPayload(BaseModel):
    title: str
    body: str = ""
    kind: str = "generic"
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> str:
        title = str(value).strip()
        if not title:
            raise ValueError("work item title must not be empty")
        return title


class WorkItem(BaseModel):
    item_id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = "generic"
    status: WorkItemStatus = WorkItemStatus.RECEIVED
    source: WorkItemSource
    payload: WorkItemPayload
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(extra="forbid")

    @field_validator("item_id", mode="before")
    @classmethod
    def _normalize_item_id(cls, value: Any) -> str:
        item_id = str(value).strip()
        if not item_id:
            raise ValueError("work item id must not be empty")
        return item_id

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        kind = str(value).strip()
        return kind or "generic"

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return [str(item).strip() for item in value if str(item).strip()]

    def with_status(self, status: WorkItemStatus) -> WorkItem:
        return self.model_copy(update={"status": status, "updated_at": utc_now()})


class FileSystemWorkItemStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def path_for(self, item_id: str) -> Path:
        return self.root / f"{item_id}.json"

    def save(self, item: WorkItem) -> Path:
        self.ensure()
        path = self.path_for(item.item_id)
        stored = item.model_copy(update={"updated_at": utc_now()})
        path.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
        return path

    def create(
        self,
        *,
        source: WorkItemSource,
        payload: WorkItemPayload,
        kind: str = "generic",
        status: WorkItemStatus = WorkItemStatus.RECEIVED,
        tags: list[str] | None = None,
    ) -> WorkItem:
        item = WorkItem(
            kind=kind,
            status=status,
            source=source,
            payload=payload,
            tags=tags or [],
        )
        self.save(item)
        return item

    def get(self, item_id: str) -> WorkItem | None:
        path = self.path_for(item_id)
        if not path.is_file():
            return None
        return WorkItem.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, *, status: WorkItemStatus | None = None, limit: int = 0) -> list[WorkItem]:
        if not self.root.is_dir():
            return []
        items: list[WorkItem] = []
        for path in sorted(self.root.glob("*.json")):
            item = WorkItem.model_validate_json(path.read_text(encoding="utf-8"))
            if status is not None and item.status is not status:
                continue
            items.append(item)
            if limit > 0 and len(items) >= limit:
                break
        return items

    def update_status(self, item_id: str, status: WorkItemStatus) -> WorkItem:
        item = self.get(item_id)
        if item is None:
            raise FileNotFoundError(item_id)
        updated = item.with_status(status)
        self.save(updated)
        return updated

    def export_summary(self) -> str:
        payload = [item.model_dump(mode="json") for item in self.list()]
        return json.dumps(payload, indent=2, ensure_ascii=False)
