"""Tests for the in-memory computation cache."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest as _  # noqa: F401

from app.utils import cache


class TestCache(unittest.TestCase):

    def setUp(self):
        from app.utils.helper_functions import GLOBAL_DF
        GLOBAL_DF["filename"] = "test_file.xlsx"
        cache.invalidate("test_file.xlsx")

    def tearDown(self):
        from app.utils.helper_functions import GLOBAL_DF
        GLOBAL_DF["filename"] = None
        cache.invalidate()

    def test_cache_hit(self):
        call_count = 0

        def expensive(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"result": kwargs.get("x", 0) * 2}

        r1 = cache.cached_call("expensive", expensive, x=5)
        r2 = cache.cached_call("expensive", expensive, x=5)
        self.assertEqual(r1, {"result": 10})
        self.assertEqual(r2, {"result": 10})
        self.assertEqual(call_count, 1, "Function should only be called once (cache hit)")

    def test_cache_miss_different_params(self):
        call_count = 0

        def expensive(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"result": kwargs.get("x", 0)}

        cache.cached_call("expensive", expensive, x=1)
        cache.cached_call("expensive", expensive, x=2)
        self.assertEqual(call_count, 2, "Different params should cause cache miss")

    def test_invalidate_clears_cache(self):
        call_count = 0

        def expensive(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        r1 = cache.cached_call("expensive", expensive, x=1)
        self.assertEqual(r1["count"], 1)

        from app.utils.helper_functions import GLOBAL_DF
        GLOBAL_DF["filename"] = "new_file.xlsx"
        cache.invalidate("new_file.xlsx")

        r2 = cache.cached_call("expensive", expensive, x=1)
        self.assertEqual(r2["count"], 2, "After invalidation, function should be called again")

    def test_stats(self):
        from app.utils.helper_functions import GLOBAL_DF
        GLOBAL_DF["filename"] = "test.xlsx"
        cache.invalidate("test.xlsx")
        cache.cached_call("f1", lambda **kw: 1, x=1)
        cache.cached_call("f2", lambda **kw: 2, x=1)
        s = cache.stats()
        self.assertEqual(s["entries"], 2)
        self.assertEqual(s["filename"], "test.xlsx")
        GLOBAL_DF["filename"] = None

    def test_df_params_excluded_from_key(self):
        """DataFrame params should not affect the cache key."""
        import pandas as pd
        call_count = 0

        def fn(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"ok": True}

        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"a": [1, 2, 3]})

        cache.cached_call("fn", fn, df_sale=df1, x=1)
        cache.cached_call("fn", fn, df_sale=df2, x=1)
        self.assertEqual(call_count, 1, "df_ params should be excluded from cache key")

    def test_invalidate_returns_count(self):
        cache.cached_call("a", lambda **kw: 1, x=1)
        cache.cached_call("b", lambda **kw: 2, x=1)
        cleared = cache.invalidate()
        self.assertEqual(cleared, 2)


if __name__ == "__main__":
    unittest.main()
