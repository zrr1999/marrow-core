"""Tests for work-item contracts and filesystem store."""

from __future__ import annotations

from pathlib import Path

from marrow_core.work_items import (
    FileSystemWorkItemStore,
    WorkItemPayload,
    WorkItemSource,
    WorkItemStatus,
)


def test_work_item_store_round_trip(tmp_path: Path) -> None:
    store = FileSystemWorkItemStore(tmp_path / "work-items")

    created = store.create(
        source=WorkItemSource(channel="feishu", system="feishu", external_id="msg-1"),
        payload=WorkItemPayload(title="New message", body="hello", kind="message"),
        tags=["inbox"],
    )

    loaded = store.get(created.item_id)

    assert loaded is not None
    assert loaded.source.channel == "feishu"
    assert loaded.payload.title == "New message"
    assert loaded.status is WorkItemStatus.RECEIVED


def test_work_item_store_updates_status_and_lists_items(tmp_path: Path) -> None:
    store = FileSystemWorkItemStore(tmp_path / "work-items")
    created = store.create(
        source=WorkItemSource(channel="manual"),
        payload=WorkItemPayload(title="Review queue"),
    )

    updated = store.update_status(created.item_id, WorkItemStatus.IN_PROGRESS)
    listed = store.list(status=WorkItemStatus.IN_PROGRESS)

    assert updated.status is WorkItemStatus.IN_PROGRESS
    assert [item.item_id for item in listed] == [created.item_id]
