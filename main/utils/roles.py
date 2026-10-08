from enum import IntFlag, auto
from fastapi import HTTPException, Depends

from main.app.user.user import UserManager


class Permission(IntFlag):
    NONE = 0

    USE_ORUNMILA = auto()

    ORUNMILA_EXTENDED_MEMORIES = auto()

    WALLET = auto()

    @classmethod
    # Kept: directly asserted in tests/test_roles.py — keep.
    def ALL(cls):
        return sum(cls)


class Roles(IntFlag):
    USER = Permission.WALLET

    PREMIUM = USER | Permission.USE_ORUNMILA | Permission.ORUNMILA_EXTENDED_MEMORIES

    DEVELOPER_STARTER = USER

    DEVELOPER_ENTERPRISE = DEVELOPER_STARTER

    ADMIN = Permission.ALL()

    @classmethod
    def checkAccess(cls, userRoles: list[str], requiredPerm: Permission) -> bool:
        userPerms = Permission.NONE
        for roleName in userRoles:
            role = roleName.upper()
            if role == "ADMIN":
                return True
            try:
                userPerms |= cls[role]
            except KeyError:
                continue
        return bool(userPerms & requiredPerm)

    @staticmethod
    def requirePermission(perm: Permission):
        async def checker(user: dict = Depends(UserManager.getCurrentUser)):
            if not Roles.checkAccess(user.get("roles", []), perm):
                raise HTTPException(status_code=403, detail=f"Missing required permission: {perm.name}")
            return user

        return checker
