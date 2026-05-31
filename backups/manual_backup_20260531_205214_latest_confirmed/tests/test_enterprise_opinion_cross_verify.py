import asyncio
import importlib.util
import types
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = BASE_DIR / "mx_skills" / "enterprise-opinion-cross-verify" / "scripts" / "cross_verify.py"
spec = importlib.util.spec_from_file_location("cross_verify_test_module", MODULE_PATH)
cross_verify = importlib.util.module_from_spec(spec)
sys.modules["cross_verify_test_module"] = cross_verify
spec.loader.exec_module(cross_verify)


def test_dedupe_merges_sources():
    leads = [
        {
            "title": "济南城市建设集团有限公司涉及债券公告",
            "publish_date": "2026-01-01",
            "source": "交易所",
            "snippet": "a",
            "keywords": ["债券公告"],
            "raw_source": "mcp",
        },
        {
            "title": "济南城市建设集团有限公司涉及债券公告",
            "publish_date": "2026-01-01",
            "source": "交易所",
            "snippet": "b",
            "keywords": ["债券公告"],
            "raw_source": "skill",
        },
    ]
    result = cross_verify.dedupe_leads(leads)
    assert len(result) == 1
    assert result[0]["matched_from"] == ["mcp", "skill"]


def test_entity_match_full_name_is_strong():
    match = cross_verify.entity_match(
        "济南城市建设集团有限公司",
        "济南城市建设集团有限公司发布2026年度债券公告。",
    )
    assert match["is_target_company"] is True
    assert match["match_level"] == "strong"


def test_entity_match_alias_with_generic_terms_is_weak():
    match = cross_verify.entity_match(
        "济南城市建设集团有限公司",
        "济南城市建设发行债券并披露募集说明书。",
    )
    assert match["is_target_company"] is False
    assert match["match_level"] == "weak"


def test_entity_match_alias_requires_two_auxiliary_conditions_for_medium():
    match = cross_verify.entity_match(
        "济南城市建设集团有限公司",
        "济南城市建设发行债券，债券代码188888.SH，济南市国资委为出资人。",
        province="山东省",
        city="济南市",
        aliases=["济南城市建设"],
        url="https://www.sse.com.cn/a.pdf",
        source="上海证券交易所",
    )
    assert match["is_target_company"] is True
    assert match["match_level"] == "medium"


def test_within_lookback_uses_beijing_date(monkeypatch):
    monkeypatch.setattr(cross_verify, "_batch_now", lambda: datetime(2026, 6, 4, 1, 0, tzinfo=cross_verify.BATCH_TZ))

    assert cross_verify._within_lookback("2026-06-03", 1) is True
    assert cross_verify._within_lookback("2026-06-02", 1) is False


def test_full_text_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "FULL_TEXT_DIR", tmp_path)
    result = {"title": "公告", "source": "交易所", "url": "https://example.com/a", "publish_date": "2026-01-01"}
    full_text_id = cross_verify.save_full_text("济南城市建设集团有限公司", result, "正文内容")
    cached = cross_verify.get_full_text(full_text_id)
    assert cached["text"] == "正文内容"
    assert cached["company_name"] == "济南城市建设集团有限公司"


def test_public_search_disabled_marks_pending(monkeypatch):
    async def fake_mcp(company_name, lookback_days):
        return [
            {
                "title": "济南城市建设集团有限公司公告",
                "publish_date": "2026-01-01",
                "source": "iFinD",
                "snippet": "摘要",
                "keywords": ["公告"],
                "raw_source": "mcp",
            }
        ], {"status": "success", "result_count": 1, "error": ""}

    async def fake_skill(company_name, lookback_days):
        return [], {"status": "skipped", "result_count": 0, "error": ""}

    monkeypatch.setattr(cross_verify, "collect_mcp_leads", fake_mcp)
    monkeypatch.setattr(cross_verify, "collect_skill_leads", fake_skill)
    output = asyncio.run(
        cross_verify.run_cross_verification(
            {
                "company_name": "济南城市建设集团有限公司",
                "sources": {"mcp": True, "skill": False, "public_search": False},
            },
            batch_context=True,
        )
    )
    assert output["verified_results"] == []
    assert output["pending_verification_results"][0]["reason"] == "public_search_disabled"


def test_direct_live_verification_disabled_by_default():
    with pytest.raises(PermissionError):
        asyncio.run(cross_verify.run_cross_verification({"company_name": "济南城市建设集团有限公司"}))


def test_wrapped_mcp_text_extracts_inner_lead_only():
    raw = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"data":{"data":"[{\\"资讯标题\\":\\"测试公告\\",\\"资讯内容\\":\\"上海世茂股份有限公司公告正文\\",\\"日期\\":\\"2026-05-29\\",\\"URL\\":\\"https://example.com/a\\"}]"}}',
                }
            ]
        }
    }
    leads = cross_verify.extract_leads(raw, "mcp", "上海世茂股份有限公司")
    assert len(leads) == 1
    assert leads[0]["title"] == "测试公告"
    assert leads[0]["possible_url"] == "https://example.com/a"


def test_collect_skill_leads_handles_list_response(tmp_path, monkeypatch):
    skill_path = tmp_path / "mx_skills" / "mx-finance-search" / "scripts"
    skill_path.mkdir(parents=True)
    (skill_path / "get_data.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(cross_verify, "BASE_DIR", tmp_path)

    class FakeModule:
        async def query_financial_news(self, **kwargs):
            return [{"title": "测试公告", "summary": "上海世茂股份有限公司公告", "URL": "https://example.com/a"}]

    monkeypatch.setattr(cross_verify, "_load_module", lambda module_path, module_name: FakeModule())

    leads, status = asyncio.run(cross_verify.collect_skill_leads("上海世茂股份有限公司", 365))

    assert status["status"] == "success"
    assert status["error"] == ""
    assert len(leads) == 1


def test_collect_skill_leads_handles_sync_response(tmp_path, monkeypatch):
    skill_path = tmp_path / "mx_skills" / "mx-finance-search" / "scripts"
    skill_path.mkdir(parents=True)
    (skill_path / "get_data.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(cross_verify, "BASE_DIR", tmp_path)

    class FakeModule:
        def query_financial_news(self, **kwargs):
            return {"items": [{"title": "同步公告", "summary": "上海世茂股份有限公司公告", "URL": "https://example.com/sync"}]}

    to_thread_calls = []

    async def fake_to_thread(func, **kwargs):
        to_thread_calls.append(func)
        return func(**kwargs)

    monkeypatch.setattr(cross_verify, "_load_module", lambda module_path, module_name: FakeModule())
    monkeypatch.setattr(cross_verify.asyncio, "to_thread", fake_to_thread)

    leads, status = asyncio.run(cross_verify.collect_skill_leads("上海世茂股份有限公司", 365))

    assert status["status"] == "success"
    assert len(leads) == 1
    assert leads[0]["title"] == "同步公告"
    assert len(to_thread_calls) == 1


def test_collect_mcp_leads_retries_with_shared_limiter(monkeypatch):
    import mcp.client as mcp_client

    calls = []

    class FakeClient:
        def __init__(self, server):
            self.server = server

        def call_tool(self, tool_name, args):
            calls.append((tool_name, args))
            if len(calls) < 3:
                raise RuntimeError("temporary failure")
            return [{"title": "测试公告", "summary": "济南城市建设集团有限公司公告"}]

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    monkeypatch.setattr(cross_verify.GLOBAL_MCP_RATE_LIMITER, "wait", lambda: None)
    monkeypatch.setattr(cross_verify.asyncio, "sleep", fake_sleep)
    monkeypatch.setenv("OPINION_MCP_SERVERS", "news")

    leads, status = asyncio.run(cross_verify.collect_mcp_leads("济南城市建设集团有限公司", 365))

    assert len(calls) == 3
    assert sleeps == [5, 15]
    assert status["status"] == "success"
    assert len(leads) == 1


def test_collect_mcp_leads_uses_beijing_date(monkeypatch):
    import mcp.client as mcp_client

    captured_args = {}

    class FakeClient:
        def __init__(self, server):
            pass

        def call_tool(self, tool_name, args):
            captured_args.update(args)
            return [{"title": "测试公告", "summary": "济南城市建设集团有限公司公告"}]

    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    monkeypatch.setattr(cross_verify.GLOBAL_MCP_RATE_LIMITER, "wait", lambda: None)
    monkeypatch.setattr(cross_verify, "_batch_now", lambda: datetime(2026, 6, 4, 1, 0, tzinfo=cross_verify.BATCH_TZ))
    monkeypatch.setenv("OPINION_MCP_SERVERS", "news")

    leads, status = asyncio.run(cross_verify.collect_mcp_leads("济南城市建设集团有限公司", 1))

    assert status["status"] == "success"
    assert captured_args["time_end"] == "2026-06-04"
    assert captured_args["time_start"] == "2026-06-03"
    assert len(leads) == 1


def test_opinion_batch_skips_outside_window(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: False)

    async def should_not_run(*args, **kwargs):
        raise AssertionError("run_cross_verification should not run outside batch window")

    monkeypatch.setattr(cross_verify, "run_cross_verification", should_not_run)
    status = asyncio.run(cross_verify.run_opinion_batch(["济南城市建设集团有限公司"]))

    assert status["status"] == "skipped"
    assert status["error"] == "outside_batch_window"


def test_skipped_batch_keeps_latest_effective_success(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    store = cross_verify.get_batch_store()
    store.save_status(
        {
            "status": "success",
            "batch_id": "success-1",
            "started_at": "2026-06-01T00:00:00+08:00",
            "finished_at": "2026-06-01T01:00:00+08:00",
            "companies_total": 1,
            "companies_completed": 1,
            "companies_failed": 0,
        }
    )
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: False)

    status = asyncio.run(cross_verify.run_opinion_batch(["济南城市建设集团有限公司"]))
    latest = store.get_latest_status()

    assert status["status"] == "skipped"
    assert latest["latest_batch_status"] == "skipped"
    assert latest["latest_effective_batch_id"] == "success-1"
    assert latest["latest_success_batch_id"] == "success-1"


def test_batch_window_uses_asia_shanghai_timezone():
    utc_time_for_beijing_midnight = datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc)
    utc_time_for_beijing_8am = datetime(2026, 6, 4, 0, 0, tzinfo=timezone.utc)

    assert cross_verify.is_batch_window(utc_time_for_beijing_midnight) is True
    assert cross_verify.is_batch_window(utc_time_for_beijing_8am) is False
    assert cross_verify.next_scheduled_run(datetime(2026, 6, 3, 23, 59, tzinfo=cross_verify.BATCH_TZ)).startswith("2026-06-04T00:00:00+08:00")


def test_opinion_batch_running_lock_skips_new_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: True)
    store = cross_verify.get_batch_store()
    store.save_status(
        {
            "status": "running",
            "batch_id": "running-1",
            "started_at": cross_verify._batch_now_iso(),
            "finished_at": "",
            "companies_total": 1,
        }
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("new batch should not start while previous batch is running")

    monkeypatch.setattr(cross_verify, "run_cross_verification", should_not_run)
    status = asyncio.run(cross_verify.run_opinion_batch(["济南城市建设集团有限公司"]))

    assert status["status"] == "skipped"
    assert status["reason"] == "previous_batch_still_running"
    assert status["running_batch_id"] == "running-1"


def test_opinion_batch_stale_running_allows_new_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: True)
    old_started = (cross_verify._batch_now() - timedelta(hours=13)).isoformat(timespec="seconds")
    store = cross_verify.get_batch_store()
    store.save_status(
        {
            "status": "running",
            "batch_id": "stale-1",
            "started_at": old_started,
            "finished_at": "",
            "companies_total": 1,
        }
    )

    async def fake_verify(params, **kwargs):
        return {"company_name": params["company_name"], "verified_results": [], "pending_verification_results": [], "rejected_results": [], "warnings": []}

    monkeypatch.setattr(cross_verify, "run_cross_verification", fake_verify)
    status = asyncio.run(cross_verify.run_opinion_batch(["济南城市建设集团有限公司"]))
    stale_status = (tmp_path / "stale-1" / "status.json").read_text(encoding="utf-8")

    assert status["status"] == "success"
    assert "stale_failed" in stale_status
    assert "batch timeout, marked as stale" in stale_status


def test_stale_lock_with_non_running_status_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: True)
    store = cross_verify.get_batch_store()
    store.save_status(
        {
            "status": "success",
            "batch_id": "success-lock",
            "started_at": "2026-06-01T00:00:00+08:00",
            "finished_at": "2026-06-01T00:10:00+08:00",
            "companies_total": 1,
            "companies_completed": 1,
            "companies_failed": 0,
        }
    )
    store.lock_path.write_text('{"batch_id":"orphan","created_at":"2026-06-01T00:00:00+08:00"}', encoding="utf-8")

    async def fake_verify(params, **kwargs):
        return {"company_name": params["company_name"], "verified_results": [], "pending_verification_results": [], "rejected_results": [], "warnings": []}

    monkeypatch.setattr(cross_verify, "run_cross_verification", fake_verify)
    status = asyncio.run(cross_verify.run_opinion_batch(["济南城市建设集团有限公司"]))

    assert status["status"] == "success"
    assert not store.lock_path.exists()


def test_opinion_batch_updates_progress_as_companies_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "is_batch_window", lambda: True)

    class RecordingStore(cross_verify.OpinionBatchStore):
        def __init__(self, base_dir):
            super().__init__(base_dir)
            self.saved_statuses = []

        def save_status(self, status):
            self.saved_statuses.append(dict(status))
            super().save_status(status)

    store = RecordingStore(tmp_path)
    monkeypatch.setattr(cross_verify, "get_batch_store", lambda: store)

    async def fake_verify(params, **kwargs):
        if params["company_name"] == "失败公司":
            raise RuntimeError("boom")
        return {"company_name": params["company_name"], "verified_results": [], "pending_verification_results": [], "rejected_results": [], "warnings": []}

    monkeypatch.setattr(cross_verify, "run_cross_verification", fake_verify)

    status = asyncio.run(cross_verify.run_opinion_batch(["成功公司", "失败公司"]))

    running_progress = [s for s in store.saved_statuses if s.get("status") == "running" and s.get("completed_companies", 0) + s.get("failed_companies", 0) > 0]
    assert running_progress
    assert status["status"] == "partial_success"
    assert status["completed_companies"] == 1
    assert status["failed_companies"] == 1


def test_cached_result_uses_latest_success_when_latest_is_running(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    store = cross_verify.get_batch_store()
    result = {"company_name": "济南城市建设集团有限公司", "verified_results": [{"title": "old"}]}
    store.save_company_result("success-1", "济南城市建设集团有限公司", result)
    store.save_status(
        {
            "status": "success",
            "batch_id": "success-1",
            "started_at": "2026-06-01T00:00:00+08:00",
            "finished_at": "2026-06-01T01:00:00+08:00",
            "companies_total": 1,
            "companies_completed": 1,
            "companies_failed": 0,
        }
    )
    store.save_status(
        {
            "status": "running",
            "batch_id": "running-2",
            "started_at": cross_verify._batch_now_iso(),
            "finished_at": "",
            "companies_total": 1,
            "companies_completed": 0,
            "companies_failed": 0,
        }
    )

    cached = cross_verify.get_cached_opinion_result("济南城市建设集团有限公司")

    assert cached["verified_results"][0]["title"] == "old"
    assert cached["cache_status"]["is_updating"] is True
    assert cached["cache_status"]["displaying_previous_batch"] is True
    assert cached["cache_status"]["running_batch_id"] == "running-2"
    assert cached["cache_status"]["data_batch_id"] == "success-1"


def test_cached_result_falls_back_to_older_success_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "BATCH_DIR", tmp_path)
    store = cross_verify.get_batch_store()
    store.save_company_result("success-old", "济南城市建设集团有限公司", {"company_name": "济南城市建设集团有限公司", "verified_results": [{"title": "older"}]})
    store.save_status(
        {
            "status": "success",
            "batch_id": "success-old",
            "started_at": "2026-06-01T00:00:00+08:00",
            "finished_at": "2026-06-01T01:00:00+08:00",
            "companies_total": 1,
            "companies_completed": 1,
            "companies_failed": 0,
        }
    )
    store.save_status(
        {
            "status": "partial_success",
            "batch_id": "partial-new",
            "started_at": "2026-06-04T00:00:00+08:00",
            "finished_at": "2026-06-04T01:00:00+08:00",
            "companies_total": 2,
            "companies_completed": 1,
            "companies_failed": 1,
        }
    )

    cached = cross_verify.get_cached_opinion_result("济南城市建设集团有限公司")

    assert cached["verified_results"][0]["title"] == "older"
    assert cached["cache_status"]["data_batch_id"] == "success-old"
    assert cached["cache_status"]["data_batch_status"] == "success"
    assert cached["cache_status"]["data_is_fallback_from_older_batch"] is True


def test_packaging_script_uses_posix_zip_paths(tmp_path):
    package_path = BASE_DIR / "scripts" / "package_enterprise_opinion_skill.py"
    spec = importlib.util.spec_from_file_location("package_enterprise_opinion_skill_test_module", package_path)
    package_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package_module)

    output = tmp_path / "skill.zip"
    package_module.package_skill(output)

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()

    assert "enterprise-opinion-cross-verify/SKILL.md" in names
    assert "enterprise-opinion-cross-verify/scripts/cross_verify.py" in names
    assert "enterprise-opinion-cross-verify/scripts/package_enterprise_opinion_skill.py" in names
    assert not any("\\" in name for name in names)
    assert package_module.validate_zip(output) == []


def test_weak_match_does_not_block_later_strong_match(tmp_path, monkeypatch):
    monkeypatch.setattr(cross_verify, "FULL_TEXT_DIR", tmp_path)

    class Searcher:
        def search(self, query, max_results=5):
            return [
                {"title": "weak", "url": "https://example.com/weak"},
                {"title": "strong", "url": "https://www.sse.com.cn/strong"},
            ]

    class Fetcher:
        def fetch(self, url):
            if "weak" in url:
                return cross_verify.PublicPage(
                    url=url,
                    title="简称新闻",
                    source="example",
                    publish_date="2026-01-01",
                    text="城投集团公告",
                )
            return cross_verify.PublicPage(
                url=url,
                title="测试公告",
                source="上交所",
                publish_date="2026-01-01",
                text="韩城城市投资（集团）有限公司 测试公告 债券",
            )

    lead = {
        "title": "测试公告",
        "publish_date": "2026-01-01",
        "source": "",
        "snippet": "",
        "keywords": ["公告"],
        "matched_from": ["skill"],
    }
    verified, pending, _, _ = cross_verify.verify_lead_with_public_pages(
        "韩城城市投资（集团）有限公司",
        lead,
        Searcher(),
        Fetcher(),
        True,
        365,
    )
    assert verified is not None
    assert verified["url"] == "https://www.sse.com.cn/strong"
    assert pending is None


def test_event_level_dedupe_prefers_official_source():
    results = [
        {
            "id": "media",
            "title": "Media report: same event amount 28.98",
            "publish_date": "2026-01-07",
            "source": "media",
            "url": "https://mp.weixin.qq.com/s/x",
            "summary": "same event amount 28.98",
            "source_excerpt": "same event amount 28.98",
            "verification_status": "verified",
        },
        {
            "id": "official",
            "title": "Official notice: same event amount 28.98",
            "publish_date": "2026-01-07",
            "source": "SSE",
            "url": "https://www.sse.com.cn/a.pdf",
            "summary": "same event amount 28.98",
            "source_excerpt": "same event amount 28.98",
            "verification_status": "verified",
        },
    ]
    deduped = cross_verify.dedupe_verified_results(results)
    assert len(deduped) == 1
    assert deduped[0]["url"] == "https://www.sse.com.cn/a.pdf"


def test_pdf_ocr_fallback_used_for_text_empty_pdf(monkeypatch):
    class FakePage:
        def extract_text(self):
            return ""

    class FakeReader:
        metadata = None
        pages = [FakePage()]

        def __init__(self, stream):
            pass

    fake_pypdf = types.SimpleNamespace(PdfReader=FakeReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)
    monkeypatch.setattr(cross_verify, "extract_pdf_text_with_ocr", lambda content: "OCR正文 上海世茂股份有限公司")

    page = cross_verify.extract_pdf_text("https://example.com/a.pdf", b"%PDF-1.4\n%%EOF")
    assert page.status == "ok"
    assert "OCR正文" in page.text


def test_official_source_searcher_extracts_official_links(monkeypatch):
    class FakeResponse:
        status_code = 200
        url = "https://www.sse.com.cn/home/search/?webswd=test"
        text = """
        <html><body>
          <a href="/disclosure/bond/announcement/company/c/new.pdf">上海世茂股份有限公司债券公告</a>
          <a href="https://example.com/noise.html">上海世茂股份有限公司公告</a>
        </body></html>
        """

    class FakeClient:
        def __init__(self, **kwargs):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            self.calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(cross_verify.httpx, "Client", FakeClient)
    monkeypatch.setattr(cross_verify, "OFFICIAL_SEARCH_TEMPLATES", [("上海证券交易所", "https://www.sse.com.cn/home/search/?webswd={query}")])
    monkeypatch.setenv("OPINION_OFFICIAL_QUERY_LIMIT", "1")

    results = cross_verify.OfficialSourceSearcher().search("上海世茂股份有限公司", max_results=5)

    assert len(results) == 1
    assert results[0]["source"] == "上海证券交易所"
    assert results[0]["url"] == "https://www.sse.com.cn/disclosure/bond/announcement/company/c/new.pdf"


def test_discovery_queries_include_city_invest_alias_and_env_extra_terms(monkeypatch):
    monkeypatch.setenv("OPINION_EXTRA_DISCOVERY_TERMS", "中原新闻网 舆情")
    queries = cross_verify.generate_discovery_queries("韩城城市投资（集团）有限公司")
    joined = "\n".join(queries)

    assert "韩城城投 工程款 拖欠 诉讼" in joined
    assert "韩城城投 中原新闻网 舆情" in joined
    assert "韩城市城市投资（集团）有限公司 关于未能按期支付债务的公告" in joined
