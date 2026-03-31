"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { StateMessage } from "@/components/StateMessage";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { loading, isAuthenticated } = useAuth();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/dashboard")}`);
    }
  }, [loading, isAuthenticated, router, pathname]);

  if (loading) {
    return <StateMessage title="Checking session" description="Please wait while we verify your access token." />;
  }

  if (!isAuthenticated) {
    return <StateMessage title="Unauthorized" description="Redirecting to login page." tone="warning" />;
  }

  return <>{children}</>;
}