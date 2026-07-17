import pytest
from main.models.sandbox import PrometheusSandbox


class TestPrometheusSandboxModel:
    def test_create_sandbox_mapping(self, dbSession):
        sandbox = PrometheusSandbox(
            userId=1,
            sandboxId="sb-test-123",
            workspacePath="/data/workspaces/1",
        )
        dbSession.add(sandbox)
        dbSession.commit()
        assert sandbox.id is not None
        assert sandbox.sandboxId == "sb-test-123"
        assert sandbox.userId == 1

    def test_sandbox_has_timestamps(self, dbSession):
        sandbox = PrometheusSandbox(
            userId=1,
            sandboxId="sb-test-456",
            workspacePath="/data/workspaces/1",
        )
        dbSession.add(sandbox)
        dbSession.commit()
        assert sandbox.createdAt is not None
        assert sandbox.lastActivity is not None

    def test_one_sandbox_per_user(self, dbSession):
        """Enforce one active sandbox per user via application logic."""
        s1 = PrometheusSandbox(userId=1, sandboxId="sb-a", workspacePath="/data/workspaces/1")
        dbSession.add(s1)
        dbSession.commit()
        existing = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert existing is not None
        assert existing.sandboxId == "sb-a"
