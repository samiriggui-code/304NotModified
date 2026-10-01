from app import admin_auth, cli


def test_set_password_replaces_only_the_hash(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ADMIN_EMAIL='moi@exemple.fr'\nADMIN_PASSWORD_HASH='ancienne'\nSESSION_SECRET='s'\n")
    answers = iter(["nouveau-mot-de-passe", "nouveau-mot-de-passe"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(answers))

    assert cli.main(["set-password", str(env)]) == 0

    lines = env.read_text().splitlines()
    assert lines[:2] == ["ADMIN_EMAIL='moi@exemple.fr'", "SESSION_SECRET='s'"]
    stored = lines[2].removeprefix("ADMIN_PASSWORD_HASH='").removesuffix("'")
    assert admin_auth.verify_password("nouveau-mot-de-passe", stored)


def test_set_password_refuses_short_or_different(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ADMIN_PASSWORD_HASH='ancienne'\n")
    for answers in (["court"], ["un-mot-de-passe-long", "un-autre-mot-de-passe"]):
        it = iter(answers)
        monkeypatch.setattr(cli.getpass, "getpass", lambda prompt, it=it: next(it))
        assert cli.main(["set-password", str(env)]) == 1
    assert env.read_text() == "ADMIN_PASSWORD_HASH='ancienne'\n"
