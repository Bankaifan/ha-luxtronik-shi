import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "ci" / "template_fetch.py"
_spec = importlib.util.spec_from_file_location("template_fetch", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

BOT = "bankaifan-agent-approver"
SHA_A = "a" * 40
SHA_B = "b" * 40
MANIFEST = '{"template": "Bankaifan/agent-template", "synced_sha": ""}'


def env(body=None, author=BOT + "[bot]", title="Template sync aaaaaaa", bot=BOT):
    body = f"Template-Sync: {SHA_A}\n" if body is None else body
    return {"ISSUE_AUTHOR": author, "ISSUE_TITLE": title, "ISSUE_BODY": body, "AUTHOR_BOT": bot}


def test_sha_is_taken_from_the_sync_line():
    assert mod.sync_sha(f"Some text\nTemplate-Sync: {SHA_A}\n") == SHA_A


def test_sha_crlf_body():
    assert mod.sync_sha(f"Text\r\nTemplate-Sync: {SHA_A}\r\n") == SHA_A


def test_last_sha_line_wins():
    assert mod.sync_sha(f"Template-Sync: {SHA_A}\nTemplate-Sync: {SHA_B}\n") == SHA_B


def test_sha_must_be_lowercase_40_hex_on_its_own_line():
    for body in (f"Template-Sync: {SHA_A.upper()}\n", f"Template-Sync: {'a' * 39}\n",
                 f"Template-Sync: {SHA_A} extra\n", f"x Template-Sync: {SHA_A}\n", "no sha here\n", "", None):
        assert mod.sync_sha(body) is None


def test_template_repo_must_be_owner_slash_repo():
    assert mod.template_repo(MANIFEST) == "Bankaifan/agent-template"
    for bad in ('{"template": "a/b/c"}', '{"template": "../x"}', '{"template": "a b/c"}',
                '{"template": "a/b\\n"}', '{"template": 7}', '{}', "not json", "[]"):
        assert mod.template_repo(bad) is None


def test_plan_for_trusted_sync_issue():
    assert mod.plan(env(), MANIFEST) == f"Bankaifan/agent-template {SHA_A}"


def test_plan_accepts_author_in_any_login_form():
    for form in (BOT, BOT + "[bot]", "app/" + BOT):
        assert mod.plan(env(author=form), MANIFEST) == f"Bankaifan/agent-template {SHA_A}"


def test_plan_nothing_for_a_stranger_issue():
    assert mod.plan(env(author="mallory"), MANIFEST) is None


def test_plan_nothing_without_configured_bot_or_author():
    assert mod.plan(env(bot=""), MANIFEST) is None
    assert mod.plan(env(author=""), MANIFEST) is None


def test_plan_nothing_without_sync_title():
    assert mod.plan(env(title="Please sync"), MANIFEST) is None


def test_plan_nothing_without_valid_sha_line():
    assert mod.plan(env(body=f"Template-Sync: {SHA_A.upper()}\n"), MANIFEST) is None


def test_plan_nothing_without_valid_manifest():
    assert mod.plan(env(), "") is None
    assert mod.plan(env(), '{"template": "a/b/c"}') is None
