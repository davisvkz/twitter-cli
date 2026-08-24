from __future__ import annotations

from twitter_cli.client import TwitterClient
from twitter_cli.parser import _deep_get, parse_timeline_response


def _make_client() -> TwitterClient:
    client = TwitterClient.__new__(TwitterClient)
    client._ct_init_attempted = True
    client._client_transaction = None
    client._request_delay = 0.0
    client._max_retries = 0
    client._retry_base_delay = 0.0
    client._max_count = 200
    return client


def test_parse_home_timeline_fixture(fixture_loader) -> None:
    payload = fixture_loader("home_timeline.json")

    tweets, cursor = parse_timeline_response(
        payload,
        lambda data: _deep_get(data, "data", "home", "home_timeline_urt", "instructions"),
    )

    assert [tweet.id for tweet in tweets] == ["1", "20"]
    assert cursor == "cursor-bottom-1"
    assert tweets[0].media[0].type == "photo"
    # note_tweet full text should be preferred over legacy.full_text for long tweets
    assert "Show More" in tweets[0].text
    assert tweets[0].text.startswith("Hello\nworld\n")
    assert tweets[0].urls == ["https://example.com/post"]
    assert tweets[1].is_retweet is True
    assert tweets[1].retweeted_by == "bob"
    assert tweets[1].quoted_tweet is not None
    assert tweets[1].quoted_tweet.id == "30"


def test_parse_home_timeline_fixture_marks_promoted_entries(fixture_loader) -> None:
    payload = fixture_loader("home_timeline.json")
    entry = payload["data"]["home"]["home_timeline_urt"]["instructions"][0]["entries"][0]
    entry["entryId"] = "promoted-tweet-1-demo"
    entry["content"]["itemContent"]["promotedMetadata"] = {"impressionId": "demo"}

    tweets, _ = parse_timeline_response(
        payload,
        lambda data: _deep_get(data, "data", "home", "home_timeline_urt", "instructions"),
    )

    assert tweets[0].is_promoted is True
    assert tweets[1].is_promoted is False


def test_parse_tweet_detail_fixture_with_nested_items(fixture_loader) -> None:
    payload = fixture_loader("tweet_detail.json")

    tweets, cursor = parse_timeline_response(
        payload,
        lambda data: _deep_get(data, "data", "threaded_conversation_with_injections_v2", "instructions"),
    )

    assert [tweet.id for tweet in tweets] == ["100", "101"]
    assert cursor == "conversation-cursor"


def test_parse_search_timeline_fixture_with_module_items(fixture_loader) -> None:
    payload = fixture_loader("search_timeline.json")

    tweets, cursor = parse_timeline_response(
        payload,
        lambda data: _deep_get(data, "data", "search_by_raw_query", "search_timeline", "timeline", "instructions"),
    )

    assert [tweet.id for tweet in tweets] == ["500"]
    assert cursor == "search-cursor"
    assert tweets[0].media[0].type == "video"
    assert tweets[0].media[0].url == "https://video-high.mp4"


def test_parse_list_timeline_fixture_with_visibility_wrapper(fixture_loader) -> None:
    payload = fixture_loader("list_timeline.json")

    tweets, cursor = parse_timeline_response(
        payload,
        lambda data: _deep_get(data, "data", "list", "tweets_timeline", "timeline", "instructions"),
    )

    assert [tweet.id for tweet in tweets] == ["700"]
    assert cursor == "list-cursor"
    assert tweets[0].author.verified is True
    assert tweets[0].lang == "zh"
    assert tweets[0].is_subscriber_only is True


def test_fetch_user_list_with_fixture(monkeypatch, fixture_loader) -> None:
    client = _make_client()
    payload = fixture_loader("followers_page.json")
    monkeypatch.setattr(client, "_graphql_get", lambda operation_name, variables, features: payload)

    users = client._fetch_user_list(
        "Followers",
        "user-id",
        20,
        lambda data: _deep_get(data, "data", "user", "result", "timeline", "timeline", "instructions"),
    )

    assert len(users) == 1
    assert users[0].screen_name == "follower1"
    assert users[0].verified is True


def test_fetch_search_users_with_fixture(monkeypatch, fixture_loader) -> None:
    client = _make_client()
    payload = fixture_loader("search_people.json")
    monkeypatch.setattr(client, "_graphql_post", lambda operation_name, variables, features=None: payload)

    users = client.fetch_search_users("searchuser", 20)

    assert [u.screen_name for u in users] == ["searchuser"]
    assert users[0].verified is True
    assert users[0].followers_count == 321


def test_parse_timeline_response_reads_module_items_entries() -> None:
    """`moduleItems` (TimelineAddToModule continuation pages) nest their payload

    directly under `item.itemContent`, not `content.itemContent` like regular
    `entries`. Regression guard: this shape used to silently parse to zero tweets.
    """
    tweet_result = {
        "__typename": "Tweet",
        "rest_id": "600",
        "core": {"user_results": {"result": {"rest_id": "u600", "legacy": {"screen_name": "moduser"}}}},
        "legacy": {
            "full_text": "module continuation tweet",
            "created_at": "Sat Mar 08 13:00:00 +0000 2026",
            "favorite_count": 1, "retweet_count": 0, "reply_count": 0, "quote_count": 0,
            "entities": {"urls": []},
        },
    }
    payload = {
        "data": {
            "instructions": [
                {
                    "type": "TimelineAddToModule",
                    "moduleItems": [
                        {
                            "entryId": "search-module-1-tweet-600",
                            "item": {"itemContent": {"tweet_results": {"result": tweet_result}}},
                        },
                    ],
                },
            ],
        },
    }

    tweets, cursor = parse_timeline_response(payload, lambda data: _deep_get(data, "data", "instructions"))

    assert [tweet.id for tweet in tweets] == ["600"]
    assert cursor is None
