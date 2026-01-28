"""
User management module.

This module provides user authentication, profile management, and identity linking.
"""

from uuid import UUID

# Legacy models (to be deprecated)
from src.users.models import APIKey, AuditLog, RefreshToken, User

# New profile models for refactored authentication
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

# New profile schemas for refactored authentication
from src.users.profile_schemas import (
    AuthProvider,
    CommunityMemberCreate,
    CommunityMemberInDB,
    CommunityMemberResponse,
    CommunityMemberStats,
    CommunityMemberUpdate,
    CommunityRole,
    UserIdentityCreate,
    UserIdentityInDB,
    UserIdentityResponse,
    UserIdentityUpdate,
    UserProfileAdminUpdate,
    UserProfileCreate,
    UserProfileInDB,
    UserProfileResponse,
    UserProfileSelfUpdate,
    UserProfileStats,
    UserProfileUpdate,
)

# Placeholder user for system-generated content (AI notes, automated actions)
# This UUID must exist in the user_profiles table for FK constraints to work
PLACEHOLDER_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

__all__ = [
    "PLACEHOLDER_USER_ID",
    "APIKey",
    "AuditLog",
    "AuthProvider",
    "CommunityMember",
    "CommunityMemberCreate",
    "CommunityMemberInDB",
    "CommunityMemberResponse",
    "CommunityMemberStats",
    "CommunityMemberUpdate",
    "CommunityRole",
    "RefreshToken",
    "User",
    "UserIdentity",
    "UserIdentityCreate",
    "UserIdentityInDB",
    "UserIdentityResponse",
    "UserIdentityUpdate",
    "UserProfile",
    "UserProfileAdminUpdate",
    "UserProfileCreate",
    "UserProfileInDB",
    "UserProfileResponse",
    "UserProfileSelfUpdate",
    "UserProfileStats",
    "UserProfileUpdate",
]
