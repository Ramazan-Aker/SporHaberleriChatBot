import httpx


async def test_health(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_source_crud_and_validation(api_client: httpx.AsyncClient) -> None:
    payload = {
        "name": "API Source",
        "url": "https://www.aspor.com.tr",
        "rss_url": "https://www.aspor.com.tr/rss/api-test.xml",
        "category": "football",
        "source_type": "news",
        "credibility_score": 8,
        "active": True,
    }
    created = await api_client.post("/sources", json=payload)
    assert created.status_code == 201
    source_id = created.json()["id"]
    assert (await api_client.get("/sources")).json()[0]["name"] == "API Source"

    updated = await api_client.put(
        f"/sources/{source_id}", json={"credibility_score": 9}
    )
    assert updated.status_code == 200
    assert updated.json()["credibility_score"] == 9

    deleted = await api_client.delete(f"/sources/{source_id}")
    assert deleted.status_code == 204
    assert (await api_client.get("/sources")).json()[0]["active"] is False

    invalid = payload | {"rss_url": "not-a-url"}
    assert (await api_client.post("/sources", json=invalid)).status_code == 422


async def test_missing_resources_and_pagination(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/articles/999")).status_code == 404
    assert (await api_client.get("/articles?offset=0&limit=10")).status_code == 200
    assert (await api_client.get("/posts?status=ready&limit=10")).status_code == 200


async def test_permission_required_source_cannot_be_activated(
    api_client: httpx.AsyncClient,
) -> None:
    payload = {
        "name": "Habertürk Spor",
        "url": "https://www.haberturk.com/spor",
        "rss_url": "https://www.haberturk.com/rss/spor.xml",
        "category": "sports",
        "source_type": "news",
        "credibility_score": 8,
        "active": True,
    }

    blocked = await api_client.post("/sources", json=payload)
    assert blocked.status_code == 422

    created = await api_client.post("/sources", json=payload | {"active": False})
    assert created.status_code == 201
    source = created.json()
    assert source["commercial_use_status"] == "restricted"
    assert source["rss_usage_status"] == "restricted"
    assert source["terms_url"] == "https://www.haberturk.com/kullanim-kosullari"

    reactivation = await api_client.put(
        f"/sources/{source['id']}", json={"active": True}
    )
    assert reactivation.status_code == 422


async def test_unreviewed_source_remains_unknown(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/sources",
        json={
            "name": "İncelenmemiş Kaynak",
            "url": "https://spor.example.com",
            "rss_url": "https://spor.example.com/rss.xml",
            "category": "sports",
            "source_type": "news",
            "credibility_score": 5,
            "active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["commercial_use_status"] == "unknown"
    assert response.json()["rss_usage_status"] == "unknown"


async def test_url_change_cannot_bypass_reviewed_source_policy(
    api_client: httpx.AsyncClient,
) -> None:
    created = await api_client.post(
        "/sources",
        json={
            "name": "Başlangıç Kaynağı",
            "url": "https://spor.example.com",
            "rss_url": "https://spor.example.com/rss.xml",
            "category": "sports",
            "source_type": "news",
            "credibility_score": 5,
            "active": True,
        },
    )
    source_id = created.json()["id"]

    updated = await api_client.put(
        f"/sources/{source_id}",
        json={
            "url": "https://www.haberturk.com/spor",
            "rss_url": "https://www.haberturk.com/rss/spor.xml",
        },
    )

    assert updated.status_code == 422
