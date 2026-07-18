import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigil.vault import Vault, PathEscapeError
from sigil import federation as F
from sigil import hatch as hatchmod


def _write(root, name, text):
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _hatch():
    d = tempfile.mkdtemp()
    hatchmod.hatch(d, "fresh")
    return d


def test_federation_resolves_link_into_remote():
    pri = _hatch()
    rem = _hatch()
    try:
        # remote has a shared note
        _write(rem, "shared.md", "---\nsource: human\n---\n# shared\nremote knowledge\n")
        # primary note links to shared AND declares share
        _write(pri, "a.md", "---\nshare: [team]\n---\nlink [[shared]] here\n")
        pv = Vault(pri)
        rv = Vault(rem)
        fed = F.FederatedVault(pv, {"team": rv})
        fed.scan()
        # link resolves into remote vault, confined to its root
        path = fed.resolve_link("shared")
        assert path.endswith("shared.md")
        assert fed.graph.remote_of.get("shared") == "team"
    finally:
        shutil.rmtree(pri, ignore_errors=True)
        shutil.rmtree(rem, ignore_errors=True)


def test_federation_escape_still_rejected():
    pri = _hatch()
    rem = _hatch()
    try:
        fed = F.FederatedVault(Vault(pri), {"team": Vault(rem)})
        fed.scan()
        # link to /etc/passwd must be rejected (confined in both vaults)
        try:
            fed.resolve_link("/etc/passwd")
            assert False, "escape should raise"
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(pri, ignore_errors=True)
        shutil.rmtree(rem, ignore_errors=True)


def test_federation_authorized_remotes():
    pri = _hatch()
    rem = _hatch()
    try:
        _write(pri, "a.md", "---\nshare: [team, other]\n---\nlink [[x]]\n")
        pv = Vault(pri)
        fed = F.FederatedVault(pv, {"team": Vault(rem)})  # only 'team' registered
        fed.scan()
        assert fed.authorized_remotes("a") == ["team"]  # 'other' not registered
    finally:
        shutil.rmtree(pri, ignore_errors=True)
        shutil.rmtree(rem, ignore_errors=True)


def test_federation_unreachable_link_raises():
    pri = _hatch()
    rem = _hatch()
    try:
        fed = F.FederatedVault(Vault(pri), {"team": Vault(rem)})
        fed.scan()
        try:
            fed.resolve_link("nonexistent")
            assert False
        except PathEscapeError:
            pass
    finally:
        shutil.rmtree(pri, ignore_errors=True)
        shutil.rmtree(rem, ignore_errors=True)
