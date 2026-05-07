from collector.parsers.telegram_parser import TelegramParser


def test_parse_telegram_static_message() -> None:
    html = """
    <div class="tgme_widget_message_wrap">
      <div class="tgme_widget_message">
        <a class="tgme_widget_message_date" href="https://t.me/FinanceNewsDaily/12345">
          <time datetime="2026-05-05T08:30:00+00:00"></time>
        </a>
        <div class="tgme_widget_message_text">
          〖新闻标题〗<br>
          完整消息正文...<br>
          <a href="https://example.com/article">阅读全文</a><br>
          <a href="https://t.me/FinanceNewsDaily">频道</a>
        </div>
        <div class="tgme_widget_message_link_preview_title">预览标题</div>
      </div>
    </div>
    """

    items = TelegramParser().parse(html)

    assert items == [
        {
            "title": "新闻标题",
            "url": "https://t.me/FinanceNewsDaily/12345",
            "summary": "〖新闻标题〗\n完整消息正文...\n阅读全文\n频道",
            "pub_str": "2026-05-05T08:30:00+00:00",
            "guid": "12345",
            "external_url": "https://example.com/article",
            "external_urls": ["https://example.com/article"],
            "preview_title": "预览标题",
            "raw_text_full": "〖新闻标题〗\n完整消息正文...\n阅读全文\n频道",
        }
    ]
