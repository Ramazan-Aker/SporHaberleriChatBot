import httpx


async def test_health(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_source_crud_and_validation(api_client: httpx.AsyncClient) -> None:
    payload = {
        "name": "API Source",
        "url": "https://example.com",
        "rss_url": "https://example.com/feed.xml",
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
