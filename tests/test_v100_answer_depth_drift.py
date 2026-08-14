"""Regression tests for the 2026-08-14 Tavily answer/depth drift.

Tavily returns ``answer: null`` for every request sent with
``search_depth="basic"`` (its default), regardless of the ``include_answer``
value. Live-probed 2026-08-14 against the real API with a valid key:

    search_depth=basic       include_answer=basic/advanced/True -> answer: null
    search_depth=fast        include_answer=advanced            -> 719 chars
    search_depth=ultra-fast  include_answer=advanced            -> 557 chars
    search_depth=advanced    include_answer=advanced            -> 1006 chars

``--mode answer`` requested an answer but never pinned a depth, so the
provider default ("basic") applied and the answer silently came back empty --
HTTP 200, ``errors=None``, 0-char answer. ``--mode finance`` / ``--mode
recall`` were unaffected because they already pin ``search_depth="advanced"``.

The guard lives at the end of ``engine._build_extra``: if an answer is
requested and the effective depth is "basic", upgrade it to "advanced".
Explicit answer-capable depths (fast / ultra-fast) are preserved so
latency-first modes keep their timing characteristics.
"""

from __future__ import annotations

from hsearch.engine import _build_extra


class TestAnswerForcesAnswerCapableDepth:
    def test_mode_answer_upgrades_basic_depth_to_advanced(self):
        extra = _build_extra("answer")
        assert extra.get("include_answer")
        assert extra["search_depth"] == "advanced", (
            "--mode answer must not ride Tavily's default basic depth; "
            "basic returns answer: null"
        )

    def test_answer_flag_alone_upgrades_depth(self):
        extra = _build_extra(None, answer=True)
        assert extra["include_answer"] is True
        assert extra["search_depth"] == "advanced"

    def test_answer_depth_advanced_still_upgrades_search_depth(self):
        # The user-facing --answer-depth controls include_answer, NOT
        # search_depth. Requesting advanced synthesis at basic search depth was
        # exactly the broken combination.
        extra = _build_extra("answer", answer=True, answer_depth="advanced")
        assert extra["include_answer"] == "advanced"
        assert extra["search_depth"] == "advanced"

    def test_answer_depth_basic_still_upgrades_search_depth(self):
        extra = _build_extra("answer", answer=True, answer_depth="basic")
        assert extra["include_answer"] == "basic"
        assert extra["search_depth"] == "advanced"


class TestAnswerCapableDepthsPreserved:
    def test_explicit_fast_depth_is_not_overridden(self):
        # fast returns a (shorter) answer -- keep the caller's latency choice.
        extra = _build_extra(None, answer=True, depth="fast")
        assert extra["search_depth"] == "fast"

    def test_explicit_ultra_fast_depth_is_not_overridden(self):
        extra = _build_extra(None, answer=True, depth="ultra-fast")
        assert extra["search_depth"] == "ultra-fast"

    def test_mode_fast_keeps_ultra_fast_even_with_answer(self):
        extra = _build_extra("fast", answer=True)
        assert extra["search_depth"] == "ultra-fast"

    def test_explicit_basic_depth_is_upgraded_when_answer_requested(self):
        # An explicit --depth basic + --answer is a contradiction Tavily
        # resolves by dropping the answer. Prefer returning the answer.
        extra = _build_extra(None, answer=True, depth="basic")
        assert extra["search_depth"] == "advanced"


class TestNoAnswerRequestedIsUntouched:
    def test_depth_untouched_when_no_answer_requested(self):
        extra = _build_extra(None)
        assert "search_depth" not in extra, (
            "must not inject a depth when no answer was requested -- that "
            "would silently make every plain search cost advanced credits"
        )

    def test_explicit_basic_depth_preserved_without_answer(self):
        extra = _build_extra(None, depth="basic")
        assert extra["search_depth"] == "basic"


class TestUnrelatedModesUnaffected:
    def test_finance_still_advanced(self):
        extra = _build_extra("finance")
        assert extra["search_depth"] == "advanced"
        assert extra["include_answer"] == "advanced"

    def test_recall_still_advanced(self):
        extra = _build_extra("recall")
        assert extra["search_depth"] == "advanced"


class TestCachePreservesProviderExtras:
    """A cache HIT must reproduce the cold-call response.

    Pre-2026-08-14 the cache stored ONLY the result list, so provider extras
    (Tavily's synthesized ``answer``, Exa's ``context``, usage) were dropped on
    every cache hit. Combined with the 900s TTL on ``--mode answer``, most real
    invocations hit cache and returned a 0-char answer with HTTP 200 and
    ``errors=None`` -- a fully silent failure.
    """

    def _roundtrip(self, stored):
        """Mimic engine._run_one's cache-hit branch against a stored value."""
        if isinstance(stored, dict):
            results = stored.get("results") or []
            extras = stored.get("extras") or {}
        else:
            results, extras = stored, {}
        out = {}
        for key in ("answer", "context", "usage"):
            val = extras.get(key)
            if val:
                out[key] = val
        return results, out

    def test_envelope_shape_restores_answer(self):
        stored = {"results": [{"title": "t", "url": "u"}], "extras": {"answer": "hello"}}
        results, extras = self._roundtrip(stored)
        assert len(results) == 1
        assert extras["answer"] == "hello"

    def test_legacy_bare_list_still_readable(self):
        # Entries written before the envelope must not crash or be lost.
        stored = [{"title": "t", "url": "u"}]
        results, extras = self._roundtrip(stored)
        assert len(results) == 1
        assert extras == {}

    def test_context_and_usage_also_preserved(self):
        stored = {
            "results": [],
            "extras": {"context": "ctx blob", "usage": {"credits": 2}},
        }
        _, extras = self._roundtrip(stored)
        assert extras["context"] == "ctx blob"
        assert extras["usage"] == {"credits": 2}
