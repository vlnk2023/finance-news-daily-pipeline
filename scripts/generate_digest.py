"""Generate a Chinese daily digest from translated news items."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore
from collector.translation.cloudflare import DEFAULT_TEXT_MODEL, CloudflareTextGenerator


DEFAULT_TIMEZONE = "Asia/Shanghai"
CATEGORY_RULES = {
    "宏观政策": ["央行", "财政", "国务院", "商务部", "政策", "利率", "通胀"],
    "市场表现": ["指数", "港股", "A股", "美股", "日经", "恒指", "收涨", "收跌"],
    "公司新闻": ["集团", "公司", "半导体", "机器人", "茅台", "泡泡玛特"],
    "外汇与商品": ["人民币", "美元", "外汇", "黄金", "原油", "商品"],
    "地缘风险": ["伊朗", "美国", "中东", "战争", "制裁", "霍尔木兹"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and store a daily digest.")
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--llm-limit", type=int, default=80)
    parser.add_argument(
        "--provider",
        choices=["cloudflare", "rule-based"],
        default=os.environ.get("DIGEST_PROVIDER", "cloudflare"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    start_at, end_at = _utc_bounds(digest_date, tz)

    store = SupabaseStore()
    items = store.fetch_digest_items(
        start_at=start_at.isoformat(),
        end_at=end_at.isoformat(),
        limit=args.limit,
    )
    print(f"[DIGEST] date={digest_date} start={start_at.isoformat()} end={end_at.isoformat()} translated_items={len(items)}")
    digest = build_digest(digest_date, items)
    if args.provider == "cloudflare" and items:
        try:
            generator = CloudflareTextGenerator()
            print(f"[DIGEST] LLM model={generator.model}")
            digest = build_llm_digest(
                digest_date,
                items[: args.llm_limit],
                generator=generator,
                fallback_digest=digest,
            )
            print(f"[DIGEST] LLM digest generated OK, length={len(digest['markdown'])}")
        except Exception as exc:
            logging.exception("LLM digest generation failed; using rule-based fallback: %s", exc)
            print(f"[DIGEST] LLM FAILED, using rule-based fallback: {exc}")

    store.upsert_daily_digest(digest)
    print(f"[DIGEST] upserted daily_digest date={digest_date} model={digest['model']}")
    print(
        json.dumps(
            {
                "digest_date": str(digest_date),
                "items": len(items),
                "model": digest["model"],
            },
            ensure_ascii=False,
        )
    )


def build_digest(digest_date: date, items: list[dict[str, str]]) -> dict[str, object]:
    categorized = {name: [] for name in CATEGORY_RULES}
    categorized["其他"] = []

    for item in items:
        category = _category_for(item)
        categorized[category].append(item)

    title = f"{digest_date.isoformat()} 财经新闻日报"
    lines = [
        f"# {title}",
        "",
        f"- 新闻数量：{len(items)}",
        f"- 生成方式：规则版日报生成器",
        "",
        "## 今日要点",
    ]
    for item in items[:8]:
        lines.append(f"- {_headline(item)}")

    for category, rows in categorized.items():
        if not rows:
            continue
        lines.extend(["", f"## {category}"])
        for item in rows[:12]:
            link = item.get("external_url") or item.get("url") or ""
            suffix = f" ([link]({link}))" if link else ""
            lines.append(f"- {_headline(item)}{suffix}")

    json_summary = {
        "date": digest_date.isoformat(),
        "item_count": len(items),
        "categories": {category: len(rows) for category, rows in categorized.items() if rows},
    }
    return {
        "digest_date": digest_date.isoformat(),
        "title": title,
        "markdown": "\n".join(lines),
        "json_summary": json_summary,
        "model": "rule-based-v1",
    }


def build_llm_digest(
    digest_date: date,
    items: list[dict[str, str]],
    *,
    generator: CloudflareTextGenerator,
    fallback_digest: dict[str, object],
) -> dict[str, object]:
    prompt = _llm_prompt(digest_date, items, fallback_digest)
    markdown = generator.generate(
        messages=[
            {
                "role": "system",
                "content": (
                    "你是严谨的中文财经与科技新闻编辑。"
                    "请只输出中文 Markdown，不要编造输入中不存在的事实。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1800,
        temperature=0.2,
    ).strip()

    if not markdown.startswith("#"):
        markdown = f"# {digest_date.isoformat()} 财经新闻日报\n\n{markdown}"

    json_summary = {
        **fallback_digest["json_summary"],
        "provider": "cloudflare",
        "llm_item_count": len(items),
    }
    return {
        "digest_date": digest_date.isoformat(),
        "title": f"{digest_date.isoformat()} 财经新闻日报",
        "markdown": markdown,
        "json_summary": json_summary,
        "model": f"cloudflare:{os.environ.get('CLOUDFLARE_DIGEST_MODEL') or DEFAULT_TEXT_MODEL}",
    }


def _llm_prompt(
    digest_date: date,
    items: list[dict[str, str]],
    fallback_digest: dict[str, object],
) -> str:
    lines = [
        f"请基于以下新闻生成 {digest_date.isoformat()} 的中文日报。",
        "",
        "输出要求：",
        "- 使用 Markdown。",
        "- 包含标题、今日总览、重点新闻、市场与宏观、科技与网络安全、风险提示、值得继续关注。",
        "- 每条结论尽量引用来源标题或链接。",
        "- 不要写免责声明，不要输出英文栏目名。",
        "- 如果某栏目没有足够信息，可以简短说明。",
        "",
        "规则版日报草稿如下，可作为参考，但请压缩重复信息并提升可读性：",
        str(fallback_digest["markdown"])[:3500],
        "",
        "结构化新闻输入：",
    ]
    for index, item in enumerate(items, start=1):
        title = item.get("title_zh") or item.get("title") or "未命名新闻"
        summary = item.get("summary_zh") or item.get("summary") or ""
        source = item.get("source_id") or ""
        link = item.get("external_url") or item.get("url") or ""
        published_at = item.get("published_at") or ""
        lines.append(
            (
                f"{index}. [{source}] {title}\n"
                f"   时间：{published_at}\n"
                f"   摘要：{_compact(summary, 260)}\n"
                f"   链接：{link}"
            )
        )
    return "\n".join(lines)


def _utc_bounds(digest_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = datetime.combine(digest_date, time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _category_for(item: dict[str, str]) -> str:
    text = f"{item.get('title_zh') or item.get('title') or ''}\n{item.get('summary_zh') or item.get('summary') or ''}"
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "其他"


def _headline(item: dict[str, str]) -> str:
    title = (item.get("title_zh") or item.get("title") or "未命名新闻").strip()
    summary = (item.get("summary_zh") or item.get("summary") or "").strip()
    if summary and summary != title:
        return f"{title}：{_compact(summary, 120)}"
    return title


def _compact(text: str, max_length: int) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= max_length:
        return compacted
    return compacted[: max_length - 1].rstrip() + "…"


if __name__ == "__main__":
    main()
