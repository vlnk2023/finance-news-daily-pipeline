import json

from collector.storage.supabase_store import SupabaseStore, _merge_existing_item_row


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.posts = []

    def post(self, endpoint, *, params, headers, data, timeout):
        self.posts.append(
            {
                "endpoint": endpoint,
                "params": params,
                "headers": headers,
                "data": json.loads(data),
                "timeout": timeout,
            }
        )
        return FakeResponse()


def test_merge_existing_item_row_preserves_translation_fields_when_content_unchanged() -> None:
    incoming = {
        "guid": "g1",
        "content_hash": "same",
        "title": "new title",
        "summary": "new summary",
        "translation_status": "pending",
        "source_lang": None,
        "title_zh": None,
        "summary_zh": None,
    }
    existing = {
        "translation_status": "translated",
        "source_lang": "en",
        "title_zh": "old zh title",
        "summary_zh": "old zh summary",
        "content_hash": "same",
    }

    merged = _merge_existing_item_row(incoming, existing)

    assert merged["translation_status"] == "translated"
    assert merged["source_lang"] == "en"
    assert merged["title_zh"] == "old zh title"
    assert merged["summary_zh"] == "old zh summary"


def test_merge_existing_item_row_resets_translation_when_content_changed() -> None:
    incoming = {
        "guid": "g2",
        "content_hash": "new-hash",
        "translation_status": "pending",
        "source_lang": None,
        "title_zh": None,
        "summary_zh": None,
    }
    existing = {
        "translation_status": "translated",
        "source_lang": "en",
        "title_zh": "old zh title",
        "summary_zh": "old zh summary",
        "content_hash": "old-hash",
    }

    merged = _merge_existing_item_row(incoming, existing)

    assert merged["translation_status"] == "pending"
    assert merged["source_lang"] is None
    assert merged["title_zh"] is None
    assert merged["summary_zh"] is None


def test_upsert_batches_rows_by_count() -> None:
    session = FakeSession()
    store = SupabaseStore(
        url="https://example.supabase.co",
        service_role_key="service-key",
        session=session,
        upsert_batch_rows=2,
        upsert_max_payload_bytes=1_000_000,
    )

    count = store._upsert(
        "news_items",
        [{"guid": f"g{index}", "title": f"title {index}"} for index in range(5)],
        on_conflict="guid",
    )

    assert count == 5
    assert [len(post["data"]) for post in session.posts] == [2, 2, 1]


def test_upsert_batches_rows_by_payload_size() -> None:
    session = FakeSession()
    store = SupabaseStore(
        url="https://example.supabase.co",
        service_role_key="service-key",
        session=session,
        upsert_batch_rows=99,
        upsert_max_payload_bytes=1200,
    )

    count = store._upsert(
        "news_items",
        [{"guid": f"g{index}", "raw_json": {"text": "x" * 900}} for index in range(3)],
        on_conflict="guid",
    )

    assert count == 3
    assert [len(post["data"]) for post in session.posts] == [1, 1, 1]
