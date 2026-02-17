def _enable_login(app):
    app.config["APP_LOGIN_ENABLED"] = True
    app.config["APP_LOGIN_USERNAME"] = "mtg"
    app.config["APP_LOGIN_PASSWORD"] = "test-password"
    app.config["APP_LOGIN_PASSWORD_HASH"] = ""


def test_login_required_redirects_to_login(client, app):
    _enable_login(app)

    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in response.headers["Location"]


def test_login_rejects_invalid_credentials(client, app):
    _enable_login(app)

    response = client.post(
        "/login",
        data={"username": "mtg", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"Ung\xc3\xbcltige Login-Daten" in response.data


def test_login_allows_access_after_success(client, app):
    _enable_login(app)

    login = client.post(
        "/login",
        data={"username": "mtg", "password": "test-password"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200


def test_mutating_route_requires_login_when_enabled(client, app):
    _enable_login(app)

    response = client.post("/groups/create", data={"group_name": "Private"})
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["code"] == "AUTH_REQUIRED"
