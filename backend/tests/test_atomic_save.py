import json
import os
import stat

import pytest


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    from config import settings

    path = tmp_path / "data.json"
    monkeypatch.setattr(settings, "DATA_FILE", str(path))
    return path


def test_save_writes_the_file_and_leaves_no_temp_file(data_file):
    import database as db

    db.save_data({"users": [], "assets": [{"id": "a"}]})

    assert json.loads(data_file.read_text())["assets"] == [{"id": "a"}]
    assert os.listdir(data_file.parent) == ["data.json"]


def test_failed_save_keeps_the_previous_file_and_removes_the_temp_file(data_file):
    import database as db

    db.save_data({"users": [], "assets": []})
    before = data_file.read_text()

    with pytest.raises(TypeError):
        db.save_data({"users": [], "assets": [object()]})  # not JSON-serialisable: json.dump raises mid-write

    assert data_file.read_text() == before
    assert os.listdir(data_file.parent) == ["data.json"]


def test_save_keeps_the_files_permissions(data_file):
    import database as db

    db.save_data({"users": []})
    os.chmod(data_file, 0o600)  # the file holds password hashes and 2FA secrets

    db.save_data({"users": [{"id": "u"}]})

    assert stat.S_IMODE(os.stat(data_file).st_mode) == 0o600


def test_the_temp_file_has_the_final_mode_before_any_data_is_written(data_file, monkeypatch):
    import database as db

    db.save_data({"users": []})
    os.chmod(data_file, 0o600)
    modes_while_writing = []
    real_dump = json.dump

    def spy(obj, f, **kwargs):
        modes_while_writing.append(stat.S_IMODE(os.fstat(f.fileno()).st_mode))
        return real_dump(obj, f, **kwargs)

    monkeypatch.setattr(json, "dump", spy)
    db.save_data({"users": []})

    assert modes_while_writing == [0o600]


def test_a_new_data_file_is_readable_by_its_owner_only(data_file):
    import database as db

    old_umask = os.umask(0o022)  # the usual default, which would leave a plain new file world-readable
    try:
        db.save_data({"users": []})
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE(os.stat(data_file).st_mode) == 0o600


def test_a_leftover_temp_file_gets_the_owner_only_mode_before_any_data_is_written(data_file, monkeypatch):
    import database as db

    leftover = str(data_file) + ".tmp"  # left behind by a crash, with a wider mode
    with open(leftover, "w") as f:
        f.write("{}")
    os.chmod(leftover, 0o644)
    modes_while_writing = []
    real_dump = json.dump

    def spy(obj, f, **kwargs):
        modes_while_writing.append(stat.S_IMODE(os.fstat(f.fileno()).st_mode))
        return real_dump(obj, f, **kwargs)

    monkeypatch.setattr(json, "dump", spy)
    db.save_data({"users": []})

    assert modes_while_writing == [0o600]
    assert stat.S_IMODE(os.stat(data_file).st_mode) == 0o600
