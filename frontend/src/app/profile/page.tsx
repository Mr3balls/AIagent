"use client";

import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ProfileCard } from "@/components/ProfileCard";
import { StateMessage } from "@/components/StateMessage";
import { useAuth } from "@/hooks/useAuth";

export default function ProfilePage() {
  const { user, loading } = useAuth();

  return (
    <ProtectedRoute>
      {loading ? (
        <StateMessage title="Loading profile" description="Fetching current user information." />
      ) : user ? (
        <ProfileCard user={user} />
      ) : (
        <StateMessage title="Profile not available" description="User data was not loaded." tone="warning" />
      )}
    </ProtectedRoute>
  );
}