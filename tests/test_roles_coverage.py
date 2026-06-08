"""Tests for main/utils/roles.py — covers requirePermission and edge cases."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from main.utils.roles import Permission, Roles


class TestCheckAccess:
    def test_admin_always_passes(self):
        assert Roles.checkAccess(["ADMIN"], Permission.VIEW_PROFILE) is True

    def test_user_has_view_profile(self):
        assert Roles.checkAccess(["USER"], Permission.VIEW_PROFILE) is True

    def test_user_lacks_prometheus(self):
        assert Roles.checkAccess(["USER"], Permission.USE_PROMETHEUS) is False

    def test_premium_has_prometheus(self):
        assert Roles.checkAccess(["PREMIUM"], Permission.USE_PROMETHEUS) is True

    def test_developer_starter_has_api(self):
        assert Roles.checkAccess(["DEVELOPER_STARTER"], Permission.STARTER_API_ACCESS) is True

    def test_developer_starter_lacks_enterprise(self):
        assert Roles.checkAccess(["DEVELOPER_STARTER"], Permission.ENTERPRISE_API_ACCESS) is False

    def test_developer_enterprise_has_all_dev(self):
        assert Roles.checkAccess(["DEVELOPER_ENTERPRISE"], Permission.ENTERPRISE_API_ACCESS) is True
        assert Roles.checkAccess(["DEVELOPER_ENTERPRISE"], Permission.EXPORT_BULK_DATA) is True

    def test_unknown_role_ignored(self):
        assert Roles.checkAccess(["NONEXISTENT"], Permission.VIEW_PROFILE) is False

    def test_multiple_roles_combined(self):
        assert Roles.checkAccess(["USER", "PREMIUM"], Permission.USE_PROMETHEUS) is True

    def test_empty_roles(self):
        assert Roles.checkAccess([], Permission.VIEW_PROFILE) is False

    def test_admin_skips_other_roles(self):
        assert Roles.checkAccess(["ADMIN", "USER"], Permission.SYSTEM_CONFIG) is True


class TestRequirePermission:
    def test_raises_403_when_missing(self):
        import asyncio

        from main.utils.roles import Roles

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

        from main.utils.roles import Roles

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
