from unittest.mock import patch

import pytest

from app.core.runtime_settings import RuntimeSettings, save_runtime_settings
from app.core.server_settings import ServerSettings, save_server_settings


@pytest.mark.parametrize(
    "save,settings",
    [
        (save_runtime_settings, RuntimeSettings()),
        (save_server_settings, ServerSettings()),
    ],
)
def test_settings_save_preserves_previous_file_on_replace_failure(
    tmp_path, save, settings
):
    path = tmp_path / "settings.yaml"
    path.write_text("previous: configuration\n")
    with patch(
        "app.core.secret_files.os.replace", side_effect=OSError("disk unavailable")
    ):
        with pytest.raises(OSError, match="disk unavailable"):
            save(settings, path)
    assert path.read_text() == "previous: configuration\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.yaml"]
