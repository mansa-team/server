import pytest
from fastapi import HTTPException
from main.utils.roles import Permission, Roles


class TestPermission:
    def test_permission_enum_values(self):
        assert Permission.NONE == 0
        assert Permission.USE_PROMETHEUS > 0
        assert Permission.PROMETHEUS_EXTENDED_MEMORIES > 0


class TestRoles:
    def test_user_has_no_permissions(self):
        assert Roles.USER == Permission.NONE
        assert not (Roles.USER & Permission.USE_PROMETHEUS)

    def test_premium_has_prometheus_permissions(self):
        assert Roles.PREMIUM & Permission.USE_PROMETHEUS
        assert Roles.PREMIUM & Permission.PROMETHEUS_EXTENDED_MEMORIES

    def test_developer_starter_has_no_permissions(self):
        assert Roles.DEVELOPER_STARTER == Permission.NONE

    def test_developer_starter_missing_prometheus(self):
        assert not (Roles.DEVELOPER_STARTER & Permission.USE_PROMETHEUS)

    def test_developer_enterprise_matches_starter(self):
        assert Roles.DEVELOPER_ENTERPRISE == Roles.DEVELOPER_STARTER

    def test_admin_has_all_permissions(self):
        assert Roles.ADMIN & Permission.ALL()
        assert Roles.ADMIN & Permission.USE_PROMETHEUS
        assert Roles.ADMIN & Permission.PROMETHEUS_EXTENDED_MEMORIES

    def test_check_access_admin_returns_true(self):
        result = Roles.checkAccess(["ADMIN"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_user_without_permission(self):
        result = Roles.checkAccess(["USER"], Permission.USE_PROMETHEUS)
        assert result is False

    def test_check_access_premium_has_prometheus(self):
        result = Roles.checkAccess(["PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_case_insensitive(self):
        assert Roles.checkAccess(["admin"], Permission.USE_PROMETHEUS) is True

    def test_check_access_invalid_role_ignored(self):
        result = Roles.checkAccess(["INVALID_ROLE", "PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_empty_roles(self):
        result = Roles.checkAccess([], Permission.USE_PROMETHEUS)
        assert result is False

    def test_check_access_multiple_roles(self):
        result = Roles.checkAccess(["USER", "PREMIUM"], Permission.USE_PROMETHEUS)
        assert result is True

    def test_check_access_unknown_role_alone_returns_false(self):
        assert Roles.checkAccess(["NONEXISTENT"], Permission.USE_PROMETHEUS) is False

    def test_check_access_admin_skips_other_roles(self):
        assert Roles.checkAccess(["ADMIN", "USER"], Permission.USE_PROMETHEUS) is True


class TestRequirePermission:
    def test_raises_403_when_missing(self):
        import asyncio

        checker = Roles.requirePermission(Permission.USE_PROMETHEUS)

        async def run():
            try:
                await checker({"roles": ["USER"]})
                return None
            except HTTPException as e:
                return e

        result = asyncio.run(run())
        assert result is not None
        assert result.status_code == 403

    def test_passes_when_has_permission(self):
        import asyncio

        checker = Roles.requirePermission(Permission.USE_PROMETHEUS)

        async def run():
            try:
                result = await checker({"roles": ["PREMIUM"]})
                return result
            except HTTPException:
                return None

        result = asyncio.run(run())
        assert result is not None
        assert result["roles"] == ["PREMIUM"]


class TestPermissionAll:
    def test_all_includes_all_permissions(self):
        all_perm = Permission.ALL()
        for perm in Permission:
            if perm == Permission.NONE:
                continue
            assert all_perm & perm, f"ALL() missing {perm.name}"


class TestRolesHierarchy:
    def test_premium_includes_user(self):
        assert Roles.PREMIUM & Roles.USER == Roles.USER

    def test_enterprise_includes_starter(self):
        assert Roles.DEVELOPER_ENTERPRISE & Roles.DEVELOPER_STARTER == Roles.DEVELOPER_STARTER

    def test_admin_includes_all(self):
        for perm in Permission:
            if perm == Permission.NONE:
                continue
            assert Roles.ADMIN & perm, f"ADMIN missing {perm.name}"
