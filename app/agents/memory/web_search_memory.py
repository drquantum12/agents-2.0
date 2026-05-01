"""
memory/web_search_memory.py
─────────────────────────────────────────────
MongoDB CRUD wrapper for the `web_search_memory` collection.

Schema change vs. the DuckDuckGo version:
  • We no longer store raw result strings.
  • Gemini grounding gives us a ready-made synthesised response + citation
    metadata in one shot, so we cache those instead.

Stored document shape:
  {
      user_id            : str,
      query              : str,          ← cache key (with user_id)
      response_text      : str,          ← Gemini's grounded answer
      sources            : [             ← grounding chunks
          { title: str, uri: str }, ...
      ],
      search_queries_used: [str, ...],   ← actual queries sent to Google
  }
"""

from typing import List, Optional
from typing_extensions import TypedDict
from pymongo.collection import Collection
from pymongo.database import Database


class GroundedSearchResult(TypedDict):
    """Return type from get_cached() and _extract_grounding()."""
    response_text:       str
    sources:             List[dict]        # [{"title": str, "uri": str}]
    search_queries_used: List[str]


class WebSearchMemoryManager:
    COLLECTION = "web_search_memory"

    def __init__(self, db: Database) -> None:
        self.col: Collection = db[self.COLLECTION]

    # ── Read ──────────────────────────────────────────────────────────────

    def get_cached(
        self,
        user_id: str,
        query: str,
    ) -> Optional[GroundedSearchResult]:
        """
        Return the cached GroundedSearchResult for (user_id, query),
        or None on a cache miss.
        """
        doc = self.col.find_one(
            {"user_id": user_id, "query": query},
            {"_id": 0},
        )
        if not doc:
            return None
        return GroundedSearchResult(
            response_text       = doc.get("response_text", ""),
            sources             = doc.get("sources", []),
            search_queries_used = doc.get("search_queries_used", []),
        )

    def get_recent(self, user_id: str, limit: int = 3) -> List[dict]:
        """
        Return the most recent `limit` searches for a user.
        Each dict has keys: query, response_text, sources, search_queries_used.
        """
        return list(
            self.col.find({"user_id": user_id}, {"_id": 0})
            .sort("_id", -1)
            .limit(limit)
        )

    # ── Write ─────────────────────────────────────────────────────────────

    def save(
        self,
        user_id:             str,
        query:               str,
        response_text:       str,
        sources:             List[dict],
        search_queries_used: List[str],
    ) -> None:
        """
        Upsert a grounded search result.
        Overwrites if the same (user_id, query) pair was cached before.
        """
        self.col.update_one(
            {"user_id": user_id, "query": query},
            {"$set": {
                "response_text":       response_text,
                "sources":             sources,
                "search_queries_used": search_queries_used,
            }},
            upsert=True,
        )

    def delete_for_user(self, user_id: str) -> None:
        """Clear all search history for a user."""
        self.col.delete_many({"user_id": user_id})
