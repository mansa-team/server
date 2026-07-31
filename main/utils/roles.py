from enum import IntFlag, auto
from fastapi import HTTPException, Depends


class Permission(IntFlag):
    NONE = 0

    USE_PROMETHEUS = auto()
    GENERATE_API_KEYS = auto()

    PROMETHEUS_EXTENDED_MEMORIES = auto()

    @classmethod
    def ALL(cls):
        return sum(cls)


class Roles(IntFlag):
    USER = Permission.NONE

    PREMIUM = USER | Permission.USE_PROMETHEUS | Permission.PROMETHEUS_EXTENDED_MEMORIES

    DEVELOPER_STARTER = USER | Permission.GENERATE_API_KEYS

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
        from main.app.user.user import UserManager

        async def checker(user: dict = Depends(UserManager.getCurrentUser)):
            if not Roles.checkAccess(user.get("roles", []), perm):
                raise HTTPException(status_code=403, detail=f"Missing required permission: {perm.name}")
            return user

        return checker
