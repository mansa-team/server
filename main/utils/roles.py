from enum import IntFlag, auto

class Permission(IntFlag):
    NONE = 0

    # User
    VIEW_PROFILE = auto()
    USE_THOTH = auto()
    USE_MAAT = auto()
    
    # Premium
    USE_PROMETHEUS = auto()
    USE_OGUM = auto()

    # Developer
    GENERATE_API_KEYS = auto()
    VIEW_DEVELOPER_TAB = auto()
    
    # Admin
    VIEW_STATS = auto()
    VIEW_ANALYTICS = auto()
    MANAGE_USERS = auto()
    SYSTEM_CONFIG = auto()

    @classmethod
    def ALL(cls):
        mask = cls.NONE
        for member in cls:
            mask |= member
        return mask

class Roles(IntFlag):
    USER = Permission.VIEW_PROFILE | Permission.USE_THOTH | Permission.USE_MAAT
    PREMIUM = USER | Permission.USE_PROMETHEUS | Permission.USE_OGUM
    DEVELOPER = USER | Permission.GENERATE_API_KEYS | Permission.VIEW_DEVELOPER_TAB
    
    ADMIN = Permission.ALL()

    @classmethod
    def checkAccess(cls, userRoles: list[str], required_perm: Permission) -> bool:
        userPerms = Permission.NONE
        for roleName in userRoles:
            try:
                userPerms |= cls[roleName.upper()].value
            except KeyError:
                continue
        return (userPerms & required_perm) == required_perm

