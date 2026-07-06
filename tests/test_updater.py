"""Testes de updater: parsing de versão, update seguro (7.1) e checagem
não bloqueante (7.2)."""

import os

from owpick.infra import updater
from owpick.infra.updater import _parse_version


class TestParseVersion:
    def test_comparacao_numerica_nao_lexicografica(self):
        assert _parse_version("1.10.0") > _parse_version("1.9.9")

    def test_igualdade(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_whitespace(self):
        assert _parse_version(" 1.2.3 \n") == (1, 2, 3)

    def test_invalida_vira_zero(self):
        assert _parse_version("abc") == (0, 0, 0)
        assert _parse_version("") == (0, 0, 0)


class TestSafeUpdateBat:
    """Update seguro com rollback (tarefa 7.1) — conteúdo do .bat gerado."""

    exe_dir = r"C:\App\OWPick"

    def _bat(self):
        return updater._build_update_bat(
            exe_dir=self.exe_dir,
            exe_path=os.path.join(self.exe_dir, "OWPick.exe"),
            source_dir=r"C:\Temp\ext\OWPick",
            ext_dir=r"C:\Temp\ext",
            zip_path=r"C:\Temp\up.zip",
        )

    def test_faz_backup_antes_de_copiar(self):
        text = "\n".join(self._bat())
        # A instalação atual é renomeada para OWPick.old ANTES do robocopy.
        backup = os.path.join(self.exe_dir, updater.BACKUP_DIR_NAME)
        internal = os.path.join(self.exe_dir, "_internal")
        move_internal = 'move "' + internal + '"'
        assert move_internal in text
        assert backup in text
        assert text.index("move ") < text.index("robocopy")

    def test_restaura_em_caso_de_falha(self):
        text = "\n".join(self._bat())
        # Bloco de rollback guardado pelo ERRORLEVEL do robocopy.
        assert "if %ERRORLEVEL% GEQ 8 (" in text
        assert "Revertendo" in text
        # Restaura o backup movendo _internal/exe de volta.
        backup_internal = os.path.join(self.exe_dir, updater.BACKUP_DIR_NAME, "_internal")
        assert 'move "' + backup_internal + '"' in text
        # E relança a versão antiga dentro do bloco de falha.
        assert "exit /b 1" in text

    def test_nao_apaga_o_backup_no_sucesso(self):
        # O backup fica para o app novo apagar (cleanup_old_backup); o .bat só
        # remove OWPick.old dentro do rollback, nunca no caminho de sucesso.
        lines = self._bat()
        # Última linha útil é o relaunch + del do próprio bat, sem rmdir do backup.
        assert lines[-1] == 'del "%~f0"'


class TestCleanupOldBackup:
    def test_ignora_quando_nao_frozen(self, monkeypatch, tmp_path):
        import sys

        # Em dev (sem frozen) não mexe em nada.
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        backup = tmp_path / updater.BACKUP_DIR_NAME
        backup.mkdir()
        monkeypatch.setattr(updater, "get_exe_dir", lambda: str(tmp_path))
        updater.cleanup_old_backup()
        assert backup.exists()  # não removido em dev

    def test_remove_backup_quando_frozen(self, monkeypatch, tmp_path):
        import sys

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        backup = tmp_path / updater.BACKUP_DIR_NAME
        (backup / "_internal").mkdir(parents=True)
        monkeypatch.setattr(updater, "get_exe_dir", lambda: str(tmp_path))
        updater.cleanup_old_backup()
        assert not backup.exists()


class TestBackgroundCheck:
    """Checagem de update não bloqueante (tarefa 7.2)."""

    def teardown_method(self):
        updater.pending_update = None

    def test_publica_pending_e_chama_callback(self, monkeypatch):
        updater.pending_update = None
        monkeypatch.setattr(
            updater,
            "_evaluate_update",
            lambda: {"version": "9.9.9", "download_url": "u", "notas": "n"},
        )
        seen = []
        thread = updater.start_background_check(on_available=seen.append)
        thread.join(timeout=2)
        assert updater.pending_update is not None
        assert updater.pending_update["version"] == "9.9.9"
        assert seen and seen[0]["version"] == "9.9.9"

    def test_sem_update_nao_publica(self, monkeypatch):
        updater.pending_update = None
        monkeypatch.setattr(updater, "_evaluate_update", lambda: None)
        seen = []
        updater.start_background_check(on_available=seen.append).join(timeout=2)
        assert updater.pending_update is None
        assert seen == []

    def test_apply_pending_sem_update_retorna_false(self):
        updater.pending_update = None
        assert updater.apply_pending_update() is False

    def test_apply_pending_com_update_chama_apply(self, monkeypatch):
        called = []
        updater.pending_update = {"version": "9.9.9", "download_url": "u", "notas": ""}
        monkeypatch.setattr(updater, "_apply_update", lambda url: called.append(url))
        assert updater.apply_pending_update() is True
        assert called == ["u"]

    def test_evaluate_newer(self, monkeypatch):
        monkeypatch.setattr(
            updater, "_fetch_version_info", lambda: {"version": "99.0.0", "download_url": "z"}
        )
        monkeypatch.setattr(updater, "get_local_version", lambda: "1.0.0")
        out = updater._evaluate_update()
        assert out is not None and out["version"] == "99.0.0"

    def test_evaluate_up_to_date(self, monkeypatch):
        monkeypatch.setattr(updater, "_fetch_version_info", lambda: {"version": "1.0.0"})
        monkeypatch.setattr(updater, "get_local_version", lambda: "1.0.0")
        assert updater._evaluate_update() is None
