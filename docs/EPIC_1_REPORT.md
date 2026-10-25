# EPIC 1 — Organizations, Multi-Tenancy and RBAC Report

## Overview
EPIC 1 implements multi-tenancy and role-based access control (RBAC) across the Stráž platform.

## Database & Schema
- **Migration `002_organizations_and_rbac.py`**:
  - `organizations` table: `id`, `name`, `slug`, `billing_email`, `plan_tier`, `subscription_status`, `created_at`.
  - `organization_members` table: `id`, `org_id`, `user_id`, `role` (`owner`, `admin`, `member`, `viewer`), `created_at`. Unique constraint `(org_id, user_id)`.
  - `organization_invitations` table: `id`, `org_id`, `email`, `role`, `token`, `expires_at`, `created_at`.
  - `apps.organization_id`: Foreign key with cascade deletion and index.

## Backend Architecture
- **Dependencies (`app/deps.py`)**:
  - `get_current_org`: Resolves tenant from `X-Organization-Id` header or user's primary workspace.
  - `require_org_role(min_role)`: Enforces role hierarchy (`owner` > `admin` > `member` > `viewer`).
- **Organizations Router (`app/routers/organizations.py`)**:
  - `GET /api/orgs`: List current user's organizations.
  - `POST /api/orgs`: Create new organization.
  - `GET /api/orgs/{org_id}/members`: List organization members.
  - `POST /api/orgs/{org_id}/invitations`: Create 7-day tokenized invitation.
  - `DELETE /api/orgs/{org_id}/members/{user_id}`: Remove member (admin/owner only, owner cannot be deleted).
  - `PATCH /api/orgs/{org_id}/members/{user_id}`: Update member role (owner only for admin promotion/demotion).
  - `POST /api/invitations/{token}/accept`: Accept workspace invitation.
- **Tenant Scoping**:
  - Apps, targets, runs, findings, and overview caches are strictly tenant-isolated.

## Frontend
- `OrganizationSwitcher.tsx`: Global workspace switcher in topbar.
- `TeamPage.tsx`: Team member listing, invitation link generator, role management.
- `InvitationPage.tsx`: Standalone acceptance screen.
- `api.ts`: Automatic injection of `X-Organization-Id` in requests.
